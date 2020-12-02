"""
WHAT THIS IS:
    Dead Reckoning budget proposal that smooths sample rates over time and allows us to weight some defenses heavier
    than others
WHAT THIS IS NOT:
    - A budgeting system that understands the deprecation of outstanding liability over time. (With this budget we
    consider a released block a 100% liability for the full 30 days)
"""

import random
import pandas as pd
import numpy as np
from typing import Tuple

BUDGET_DAYS = 30  # denominator of the budget
BUDGET_MONEY = 10000  # numerator of the budget
AVG_TX_COUNT_PER_DAY = 1000  # Average number of blocked transactions per day
MAX_TX_AMOUNT = 500  # The max send_amount we want to release
DAYS_TO_SIMULATE = 90  # Number of days to simulate


class Trasaction:
    """
    Simulates a random flag_and_block transaction

    d1 - d4 are simulations of four different defenses each with their own block rate
    send_amount_usd is the simulated dollar amount randomly pulled from a triangle distrubition
                    meant to simulate SendWaves transaction shape
    """

    def __init__(self):
        first = True
        # We assume that every transaction that we look at in this simulation has been blocked for something
        # Therefore we keep looping until at least one of the defenses is randomly assigned a block
        while first or np.array([self.d1, self.d2, self.d3, self.d4]).sum().astype(bool) is False:
            first = False
            self.d1 = True if random.random() < .5 else False
            self.d2 = True if random.random() < .1 else False
            self.d3 = True if random.random() < .01 else False
            self.d4 = True if random.random() < .1 else False
        self.send_amount_usd = np.random.triangular(1, 100, 1000)


class Defense:
    """
    Represents one defense (or blocking flag) in the defense system.

    name: unique identifier for defense
    budget_money: total budget * the allocation for this defense
    budget_day: the number of rolling days the budget_money needs to span
    """

    def __init__(self, name, budget_money, budget_days):
        self.name = name
        self.budget_money = budget_money
        self.budget_days = budget_days

    def average_historical_send_amount(self, h_tx: pd.DataFrame, day: int) -> float:
        """
        The average cost of a block release
        :param h_tx: Historical dataset
        :param day: represent the chronological day in simulation history
        :return: mean send amount for transactions blocked by this defense
        """
        defense_tx = self.defense_tx(h_tx)
        return defense_tx[(defense_tx['day'] >= max(day - self.budget_days, 0)) &
                          (defense_tx['send_amount_usd'] <= MAX_TX_AMOUNT)].send_amount_usd.mean()

    def target_rate(self, h_tx: pd.DataFrame, day: int) -> int:
        """
        The ideal number of blocks by this defense that we should release in 1 day
        :param h_tx: Historical dataset
        :param day: represent the chronological day in simulation history
        :return: ideal releases per day
        """
        rate = self.budget_money / (self.average_historical_send_amount(h_tx, day) * self.budget_days)
        # rate is multiplied by 10 to increase resolution when comparing
        # plus 1 is added to the rate to try and offset the effect of the budget never being allowed to be
        # larger than BUDGET_MONEY and therefore some example are lost
        return (rate * 10) + 1

    def threshold(self, transaction: Trasaction, h_tx: pd.DataFrame, day: int) -> float:
        """
        If this defense blocked this transaction then return:
                    target rate -> a threshold value that should give us an approximatly optimum number of releases
                                    per day
        If this defense did not block this transaction then return:
                    0 -> Within the scope of THIS DEFENSE we do not is any value in collecting this sample

        :param transaction: Blocked transaction in question
        :param h_tx: Historical dataset
        :param day: represent the chronological day in simulation history
        :return: threshold used to determine if block should be released or not
        """
        if getattr(transaction, self.name):
            return self.target_rate(h_tx, day)
        return 0.0

    def average_count_per_day(self, h_tx: pd.DataFrame) -> int:
        """
        The average number of opportunities we have to release a block by this flag in a given day
        :param h_tx: Historical dataset
        :return: the average count of transactions per day where this defense was positive
        """
        defense_tx = h_tx.loc[h_tx[self.name] == True]
        daily_counts = defense_tx.groupby('day').send_amount_usd.count()
        return int(daily_counts.mean())

    def random_value(self, h_tx: pd.DataFrame) -> int:
        """
        Get a random value from 0 to average-count-of-blocks-per-day for each defense
        Note: the true average is multipled by ten to improve resolution
        :param h_tx: Historical dataset
        :return: random int
        """
        return random.randint(0, self.average_count_per_day(h_tx) * 10)

    def defense_tx(self, h_tx: pd.DataFrame) -> pd.DataFrame:
        """
        A subset of the historical dataset that contains only transactions where this defense was positive.
        :param h_tx: Historical dataset
        :return:
        """
        return h_tx.loc[h_tx[self.name] == True]


class Budget:
    """
    Dead Reckoning Budget

    budget_money: Maximum outstanding liability that can be present in a time span of budget_days
    budget_days: Number of days to consider when summing outstanding liability
    defenses: list of defense objects registered to this budget
    """

    def __init__(self, budget_money: float, budget_days: int) -> None:
        self.budget_money = budget_money
        self.budget_days = budget_days
        self.defenses = []

    def budget_allocation(self) -> Tuple[float, float]:
        """
        Return the percentage of the total budget allocated / not allocated
        :return: percent of budget claimed by registered defenses, percent of budget not claimed by register defenses
        """
        total_allocated = np.array([d.budget_money for d in self.defenses]).sum() / self.budget_money
        not_allocated = 1 - total_allocated
        return total_allocated, not_allocated

    def add_defense(self, name: str, allocation: float) -> None:
        """
        Add a defense to the budget
        :param name: unique identified for the defense
        :param allocation: relative weight of the budget that should be dedicated to samples of this defense
        :return: None
        """
        if allocation + self.budget_allocation()[0] > 1:
            raise Exception(f"This defenses budget of {allocation} plus the already allocated "
                            f"budget of {self.budget_allocation()[0]} is greater than 1")

        self.defenses.append(Defense(name, allocation * self.budget_money, self.budget_days))

    def remove_defense(self, name: str) -> None:
        """
        Unregister defense from budget
        :param name: unique identifier of defense to be removed
        :return: None
        """
        temp = []
        found = False
        for i, d in enumerate(self.defenses):
            if d.name != name:
                temp.append(d)
        if not found:
            print(f"Warning defense {name} not found")
        self.defenses = temp


budget = Budget(BUDGET_MONEY, BUDGET_DAYS)
budget.add_defense(name='d1', allocation=.1)
budget.add_defense(name='d2', allocation=.3)
budget.add_defense(name='d3', allocation=.55)
budget.add_defense(name='d4', allocation=.05)

print(f"{budget.budget_allocation()[0]}% of the budget is allocated {budget.budget_allocation()[1]}% is not")


def evaluate_if_released(tx, day, h_tx, r_tx):
    """ The evaluation function returns if this block should be released or continue on as normal

    :param tx: send_amount of transaction being evaluated
    :param day: simulated date of current tx
    :param h_tx: dataframe of all historical transactions
    :param r_tx: datafrome of all transactions released by Dead Reckoning
    :return: True or False if the tx should be released
    """

    # Get the cutoff threshold for each defense in the budget
    thresholds = np.array([d.threshold(tx, h_tx, day) for d in budget.defenses])

    # Get a random value from 0 to average-count-of-blocks-per-day for each defense
    random_values = np.array([d.random_value(h_tx) for d in budget.defenses])

    # Get the maximum dollar amount allowed to be spent
    total_budget = budget.budget_money

    # If the send_amount in USD is greater than our limit the block is not considered for release.
    # If releasing this block would put us over the total budget it is not considered for release.
    # If any one of the random values issued by all the defense in the budget is above the threshold for
    # that same defense the block is released.
    if tx.send_amount_usd <= MAX_TX_AMOUNT and r_tx[
        r_tx['day'] >= max(day - BUDGET_DAYS, 1)].send_amount_usd.sum() + tx.send_amount_usd <= total_budget \
            and (random_values < thresholds).sum().astype(bool):
        print(f"Transaction {tx.send_amount_usd} dollars was released --> "
              f"Thresholds: {thresholds} random_values: {random_values}")
        return True
    return False


def print_results(released_tx: pd.DataFrame) -> None:
    """
    Print the final results
    :param released_tx:
    :return:
    """
    avg_outstanding_liability = 0
    for day in range(released_tx.day.max() + 1):
        outstanding_liability = released_tx[(released_tx['day'] >= max(day - BUDGET_DAYS, 1)) &
                                            (released_tx['day'] < day)].send_amount_usd.sum()
        print(f"day: {day}  {BUDGET_DAYS}-day budget result: {outstanding_liability}")
        if day > BUDGET_DAYS * 2:
            avg_outstanding_liability += outstanding_liability
    print(f"Average Outstanding Liability: {avg_outstanding_liability / (day - BUDGET_DAYS * 2)}")


def print_progress(day: int, historical_tx: pd.DataFrame, released_tx: pd.DataFrame) -> None:
    """
    Print the in progress results
    :param day: simulated date of current tx
    :param historical_tx: dataframe of all historical transactions
    :param released_tx: datafrome of all transactions released by Dead Reckoning
    :return:
    """
    print(f"Working on day {day - BUDGET_DAYS} consumed "
          f"{released_tx[released_tx['day'] >= max(day - BUDGET_DAYS, 1)].send_amount_usd.sum()}")
    for d in budget.defenses:
        print(f"{d.name}: {d.defense_tx(released_tx).send_amount_usd.sum()} "
              f"release_count:  {d.defense_tx(released_tx).send_amount_usd.count()}   "
              f"historical_count:  {d.defense_tx(historical_tx).send_amount_usd.count()}")


def init_historical():
    """
    Build a history of transactions that can be used to calculate values like defense.threshold and
    defense.random_value
    :return: dataframe with simulated transactions
    """
    print("Building Historical Dataset")
    historical_tx = pd.DataFrame()
    for day in range(1, BUDGET_DAYS + 1):
        for i in range(AVG_TX_COUNT_PER_DAY):
            tx = Trasaction()
            record = tx.__dict__
            record['day'] = day
            historical_tx = historical_tx.append(pd.DataFrame(record, index=[0]), ignore_index=True)
    return historical_tx


def simulate() -> None:
    """
    Simulate results of using this budget
    :return: None
    """
    historical_tx = init_historical()
    released_tx = pd.DataFrame(columns=historical_tx.columns)  # collection of blocked transactions that were released
    for day in range(historical_tx.day.max() + 1, DAYS_TO_SIMULATE):
        print_progress(day, historical_tx, released_tx)
        for i in range(AVG_TX_COUNT_PER_DAY):
            tx = Trasaction()
            record = tx.__dict__
            record['day'] = day
            if evaluate_if_released(tx, day, historical_tx, released_tx):
                released_tx = released_tx.append(pd.DataFrame(record, index=[0]), ignore_index=True)
            historical_tx = historical_tx.append(pd.DataFrame(record, index=[0]), ignore_index=True)
    print(f"Released {len(released_tx)} Summing ${released_tx.send_amount_usd.sum()}")
    print_results(released_tx)
    print(f"Simulated {len(historical_tx)} transactions totaling ${historical_tx.send_amount_usd.sum()}")


if __name__ == '__main__':
    simulate()
