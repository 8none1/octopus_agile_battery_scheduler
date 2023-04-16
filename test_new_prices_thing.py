#!/usr/bin/env python3

import unittest
import json
import os
import copy

from new_prices_thing import plan, calculation

with open(os.path.join(os.path.dirname(__file__), "octopus_test_data.json")) as fp:
    OCTOPUS_DATA = json.load(fp)

def get_octopus_data_file():
    return copy.deepcopy(OCTOPUS_DATA)

def get_standard_octopus_data(start_time, end_time):
    data = get_octopus_data_file()
    return data

def get_all_free_octopus_data(start_time, end_time):
    data = get_octopus_data_file()
    for item in data["results"]:
        item["value_inc_vat"] = -1
    return data

def get_all_cheap_octopus_data(start_time, end_time):
    data = get_octopus_data_file()
    for item in data["results"]:
        item["value_inc_vat"] = 9
    return data

def get_mixed_octopus_data(start_time, end_time):
    data = get_octopus_data_file()
    for index, item in enumerate(data["results"]):
        if index < 16:
            item["value_inc_vat"] = -1
        elif index < 32:
            item["value_inc_vat"] = 9
        else:
            pass
            # don't do anything
    return data

class TestBasic(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(2, 2)

class TestPlan(unittest.TestCase):
    def test_standard_plan(self):
        CURRENT_BATTERY_PC_FULL = 1
        TOMORROW_SOLAR_FORECAST_KWH = 16
        plan_dict = plan(electricity_provider_fn=get_standard_octopus_data,
                         get_forecast_fn=lambda: TOMORROW_SOLAR_FORECAST_KWH,
                         get_battery_charge_fn=lambda: CURRENT_BATTERY_PC_FULL)
        self.assertEqual(len(plan_dict["free"]), 0)
        self.assertEqual(len(plan_dict["all"]), 48)
        self.assertEqual(len(plan_dict["less_than_gas"]), 0)
        self.assertEqual(plan_dict["shortfall"], 4)
        self.assertEqual(plan_dict["battery_kwh_remaining"], CURRENT_BATTERY_PC_FULL)
        self.assertEqual(plan_dict["all"].iloc[0]["cost"], 231525)
        self.assertEqual(plan_dict["daily_load"], 20)

    def test_all_free_plan(self):
        CURRENT_BATTERY_PC_FULL = 1
        TOMORROW_SOLAR_FORECAST_KWH = 16
        plan_dict = plan(electricity_provider_fn=get_all_free_octopus_data,
                         get_forecast_fn=lambda: TOMORROW_SOLAR_FORECAST_KWH,
                         get_battery_charge_fn=lambda: CURRENT_BATTERY_PC_FULL)
        self.assertEqual(len(plan_dict["free"]), 48)
        self.assertEqual(len(plan_dict["all"]), 48)
        self.assertEqual(len(plan_dict["less_than_gas"]), 48)
        self.assertEqual(plan_dict["shortfall"], 4)
        self.assertEqual(plan_dict["battery_kwh_remaining"], CURRENT_BATTERY_PC_FULL)
        self.assertEqual(plan_dict["all"].iloc[0]["cost"], -10000)
        self.assertEqual(plan_dict["daily_load"], 20)

    def test_all_cheap_plan(self):
        CURRENT_BATTERY_PC_FULL = 1
        TOMORROW_SOLAR_FORECAST_KWH = 16
        plan_dict = plan(electricity_provider_fn=get_all_cheap_octopus_data,
                         get_forecast_fn=lambda: TOMORROW_SOLAR_FORECAST_KWH,
                         get_battery_charge_fn=lambda: CURRENT_BATTERY_PC_FULL)
        self.assertEqual(len(plan_dict["free"]), 0)
        self.assertEqual(len(plan_dict["all"]), 48)
        self.assertEqual(len(plan_dict["less_than_gas"]), 48)
        self.assertEqual(plan_dict["shortfall"], 4)
        self.assertEqual(plan_dict["battery_kwh_remaining"], CURRENT_BATTERY_PC_FULL)
        self.assertEqual(plan_dict["all"].iloc[0]["cost"], 90000)
        self.assertEqual(plan_dict["daily_load"], 20)

    def test_mixed_plan(self):
        CURRENT_BATTERY_PC_FULL = 1
        TOMORROW_SOLAR_FORECAST_KWH = 16
        plan_dict = plan(electricity_provider_fn=get_mixed_octopus_data,
                         get_forecast_fn=lambda: TOMORROW_SOLAR_FORECAST_KWH,
                         get_battery_charge_fn=lambda: CURRENT_BATTERY_PC_FULL)
        self.assertEqual(len(plan_dict["free"]), 16)
        self.assertEqual(len(plan_dict["all"]), 48)
        self.assertEqual(len(plan_dict["less_than_gas"]), 32)
        self.assertEqual(plan_dict["shortfall"], 4)
        self.assertEqual(plan_dict["battery_kwh_remaining"], CURRENT_BATTERY_PC_FULL)
        self.assertEqual(plan_dict["all"].iloc[0]["cost"], 231525)
        self.assertEqual(plan_dict["daily_load"], 20)


if __name__ == "__main__":
    unittest.main()
