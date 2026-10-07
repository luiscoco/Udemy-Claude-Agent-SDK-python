"""Deliberately buggy Python fixture for the plan/command teaching exercises."""


def total(items):
    total_amount = 0
    for index in range(len(items) + 1):
        total_amount += items[index]["price"] * items[index]["qty"]
    return total_amount


def apply_discount(amount, percent):
    return amount - percent
