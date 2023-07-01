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

def get_two_free_period_octopus_data(start_time, end_time):
    "This has a free period of 1h30m at 1am and of 3h at 8.30am"
    data = get_octopus_data_file()
    values_to_set = [
        {"start_time": "2023-03-28T01:00:00Z",
         "number_of_slots": 3,
         "value_to_set": -1},
        {"start_time": "2023-03-28T08:30:00Z",
         "number_of_slots": 6,
         "value_to_set": -1},
    ]

    for value in values_to_set:
        # find the index of the slot with this start_time
        slot_index = None
        for index, item in enumerate(data["results"]):
            if item["valid_from"] == value["start_time"]:
                slot_index = index
        if slot_index is None:
            raise Exception((f"You specified a start_time ({value['start_time']}) which "
                             "doesn't correspond to a slot in the Octopus data"))
        # set the slot value for this slot and the N after it in time (before it in JSON)
        for inc in range(value["number_of_slots"]):
            data["results"][slot_index - inc]["value_inc_vat"] = value["value_to_set"]

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

class TestCalculations(unittest.TestCase):
    def test_standard_calculations(self):
        CURRENT_BATTERY_PC_FULL = 1
        TOMORROW_SOLAR_FORECAST_KWH = 16
        plan_dict = plan(electricity_provider_fn=get_standard_octopus_data,
                         get_forecast_fn=lambda: TOMORROW_SOLAR_FORECAST_KWH,
                         get_battery_charge_fn=lambda: CURRENT_BATTERY_PC_FULL)
        calc_dict = calculation(plan_dict)
        self.assertEqual(len(calc_dict["battery_charge_slots"]), 4)
        self.assertEqual(len(calc_dict["hot_water_slots"]), 0)
        self.assertEqual(len(calc_dict["dishwasher_slots"]), 0)
        self.assertEqual(calc_dict["max_battery_charge_percent"], 36)
        self.assertEqual(len(plan_dict["all"]), 48)

    def test_all_free_calculations(self):
        CURRENT_BATTERY_PC_FULL = 1
        TOMORROW_SOLAR_FORECAST_KWH = 16
        plan_dict = plan(electricity_provider_fn=get_all_free_octopus_data,
                         get_forecast_fn=lambda: TOMORROW_SOLAR_FORECAST_KWH,
                         get_battery_charge_fn=lambda: CURRENT_BATTERY_PC_FULL)
        calc_dict = calculation(plan_dict)
        self.assertEqual(len(calc_dict["battery_charge_slots"]), 48)
        self.assertEqual(len(calc_dict["hot_water_slots"]), 48)
        self.assertEqual(calc_dict["hot_water_slots"].iloc[0]["start_time"].isoformat(),
                         "2023-03-28T00:00:00+00:00")
        self.assertEqual(calc_dict["dishwasher_slots"].iloc[0]["start_time"].isoformat(),
                         "2023-03-28T00:00:00+00:00")

    def test_dishwasher_second_period_calculations(self):
        CURRENT_BATTERY_PC_FULL = 1
        TOMORROW_SOLAR_FORECAST_KWH = 16
        plan_dict = plan(electricity_provider_fn=get_two_free_period_octopus_data,
                         get_forecast_fn=lambda: TOMORROW_SOLAR_FORECAST_KWH,
                         get_battery_charge_fn=lambda: CURRENT_BATTERY_PC_FULL)
        calc_dict = calculation(plan_dict)
        self.assertEqual(len(calc_dict["battery_charge_slots"]), 9)
        self.assertEqual(len(calc_dict["hot_water_slots"]), 9)
        self.assertEqual(calc_dict["hot_water_slots"].iloc[0]["start_time"].isoformat(),
                         "2023-03-28T01:00:00+00:00")
        self.assertEqual(calc_dict["hot_water_slots"].iloc[1]["start_time"].isoformat(),
                         "2023-03-28T01:30:00+00:00")
        self.assertEqual(calc_dict["dishwasher_slots"].iloc[0]["start_time"].isoformat(),
                         "2023-03-28T08:30:00+00:00")


if __name__ == "__main__":
    unittest.main()
