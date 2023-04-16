#!/usr/bin/env python3

import sys
import requests
import pandas as pd
import datetime
import pytz
from argparse import ArgumentParser
import math

__version__ = '0.0.1'
gas_price = 10.2 * 10000 # pence per kWh
POWER_RESERVE_IN_CASE_OF_POWERCUT_HOURS = 2
BATTERY_CHARGE_RATE = 2.7 # kW/h
BATTERY_CAPACITY = 13 # kWh

def plan():
    # Get the prices from Octopus
    electricity_prices_slots = get_prices_from_octopus() # returns a pandas dataframe
    free_electricity_slots   = electricity_prices_slots.drop(electricity_prices_slots[electricity_prices_slots.cost  > 0].index)
    less_than_gas_slots      = electricity_prices_slots.drop(electricity_prices_slots[electricity_prices_slots.cost  > gas_price].index)
    slots_dict = {'all': electricity_prices_slots, 'free': free_electricity_slots, 'less_than_gas': less_than_gas_slots}
    slots_dict['shortfall'] = get_shortfall()
    slots_dict['battery_kwh_remaining'] = get_current_battery_charge()
    slots_dict['daily_load'] = get_lifetime_average_daily_load()
    return slots_dict

def calculation(slots_dict):
    battery_kwh_remaining    = get_current_battery_charge()
    free_electricity_slots   = slots_dict['free']
    less_than_gas_slots      = slots_dict['less_than_gas']
    electricity_prices_slots = slots_dict['all']
    shortfall                = slots_dict['shortfall']
    battery_kwh_remaining    = slots_dict['battery_kwh_remaining']
    daily_load               = slots_dict['daily_load']

    print(f"Shortfall: {shortfall}")
    print(f"Current battery charge: {battery_kwh_remaining}")
    print(f"Daily load: {daily_load}")

    
    buffer_kwh = POWER_RESERVE_IN_CASE_OF_POWERCUT_HOURS / 24 * daily_load # 2 hours of buffer.
    power_needed = (shortfall + buffer_kwh) - battery_kwh_remaining
    slots_needed = math.ceil(power_needed / (BATTERY_CHARGE_RATE / 2))
    print(f"Slots needed: {slots_needed}")

    if len(free_electricity_slots) >= slots_needed:
        battery_charge_slots = free_electricity_slots.copy()
    else:
        battery_charge_slots = electricity_prices_slots.copy()
        battery_charge_slots.sort_values(by=['cost'], inplace=True)
        battery_charge_slots = battery_charge_slots.head(slots_needed)
        battery_charge_slots.sort_values(by=['start_time'], inplace=True)
        print(f"Battery charge slots: {battery_charge_slots}")
    
    hot_water_slots = less_than_gas_slots.copy()
    hot_water_slots.sort_values(by=['start_time'], inplace=True)
    if not hot_water_slots.empty:
        hot_water_slots.reset_index(drop=True, inplace=True)
        slot_duration = hot_water_slots.head(1)['duration']
        hot_water_slots['grp_time'] = hot_water_slots.end_time.diff().dt.seconds.gt(slot_duration.dt.seconds[0]).cumsum()
        hot_water_slots = hot_water_slots.groupby('grp_time').agg({'start_time': 'min', 'end_time': 'max', 'cost': 'mean', 'duration': 'sum'})
        hot_water_slots = hot_water_slots.reset_index(drop=True)
        print(f"Merged slots:\n {hot_water_slots}")
        hot_water_times_list = []
        for index, row in hot_water_slots.iterrows():
            duration = row['duration']
            start_time = row['start_time']
            if duration <= datetime.timedelta(minutes=120):
                hot_water_times_list.append((start_time, duration))
            else:
                print("Too long, do something")
            
    

    battery_charge_slots = pd.concat([battery_charge_slots, hot_water_slots])
    battery_charge_slots.sort_values(by=['start_time'], inplace=True)
    battery_charge_slots = battery_charge_slots.drop_duplicates(subset=['start_time'], keep=False)
    max_battery_charge_percent = math.ceil((power_needed / BATTERY_CAPACITY) * 100)

    dishwasher_slots = battery_charge_slots.copy()
    dishwasher_slots = dishwasher_slots.rolling('2h', min_periods=4, on='start_time').mean()
    dishwasher_slots = dishwasher_slots.dropna()
    dishwasher_slots.sort_values(by=['start_time'], inplace=True)

    calculation_dict = {'battery_charge_slots': battery_charge_slots, 'hot_water_slots': hot_water_slots, 'dishwasher_slots': dishwasher_slots, 'max_battery_charge_percent': max_battery_charge_percent, 'all_slots': electricity_prices_slots}
    return calculation_dict


def execute(calculation_dict):
    battery_charge_slots = calculation_dict['battery_charge_slots']
    hot_water_slots      = calculation_dict['hot_water_slots']
    dishwasher_slots     = calculation_dict['dishwasher_slots']
    max_battery_charge_percent = calculation_dict['max_battery_charge_percent']
    all_slots            = calculation_dict['all_slots']

    print(f"Max battery charge percent: {max_battery_charge_percent}")
    print(f"Hot water slots: {hot_water_slots}")
    print(f"Dishwasher slots: {dishwasher_slots}")
    print(f"Battery charge slots: {battery_charge_slots}")



def get_prices_from_octopus(start_time = None, end_time = None):
    # Get the prices from Octopus
    # TODO: move the product code etc to either a config file or a command line argument, or pull it from the API
    if start_time is None:
        start_time = datetime.datetime.now(pytz.utc)
        start_time = start_time.replace(minute=0, second=0)
    if end_time is None:
        end_time = start_time + datetime.timedelta(days=1)
    start_time = start_time.isoformat(timespec='seconds')# + "Z"
    end_time = end_time.isoformat(timespec='seconds')# + "Z"
    print(f"Start time: {start_time}")
    print(f"End time: {end_time}")

    base_url = "https://api.octopus.energy/v1"
    product_code = "AGILE-FLEX-22-11-25"
    tariff_code = "E-1R-AGILE-FLEX-22-11-25-A" # https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25
    
    agile_price_url = f"{base_url}/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/"
    url_params = {
        "period_from": start_time,
        "period_to": end_time
    }
    r = requests.get(agile_price_url, params=url_params)
    if r.status_code == 200:
        prices_dict = r.json()
        start_time_list = pd.DatetimeIndex(x['valid_from'] for x in prices_dict['results'])
        end_time_list   = pd.DatetimeIndex(x['valid_to']   for x in prices_dict['results'])
        value_inc_vat   = [x['value_inc_vat']*10000 for x in prices_dict['results']]
        electricity_prices_slots = pd.DataFrame({'start_time':start_time_list, 'end_time': end_time_list, 'cost': value_inc_vat})
        electricity_prices_slots['duration'] = electricity_prices_slots.end_time - electricity_prices_slots.start_time
        electricity_prices_slots.set_index('start_time', inplace=True)
        electricity_prices_slots.sort_values(by=['start_time'], inplace=True)
        return electricity_prices_slots
    
    else:
        print(f"Body: {r.text}")
        raise Exception(f"Failed to get Octopus prices. Error: {r.status_code}")

def get_forecast_solar_prediction():
    url = "https://api.forecast.solar/estimate/watthours/day/52.1322466021396/-0.21998598515728754/27/-80/6.720"
    # Might change this to use the per-hour data.  Then we can see how much solar is left for the day.
    # That might mean signing up for an account, then we can hit the API once a minute if we really want to
    headers = {"Accept": "application/json"}
    r = requests.get(url, headers=headers)
    wh = r.json()['result'][(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')]
    return wh / 1000

def get_lifetime_average_daily_load():
    return 20
    if not MODBUS:
        return False
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    runtime    = client.read_input_registers(57, 2, slave=1).registers
    total_load = client.read_input_registers(1062, 2, slave=1).registers
    client.close()
    runtime = ((runtime[0] << 16 | runtime[1]) / 2) / 60 / 60 # Reading is in 0.5 second increments.  Convert to hours.
    total_load = (total_load[0] << 16 | total_load[1]) / 10 # Reading is in 0.1kWh increments.  Convert to kWh.
    print(f"Total inverter running time: {runtime} hours\nTotal load: {total_load} kWh")
    average_load = total_load / runtime # per hour
    average_load = average_load * 24
    print(f"Average load per day: {average_load} kWh")
    return average_load

def get_local_load_today():
    # if not MODBUS:
    #     return False
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    results = client.read_input_registers(1060, 2, slave=1).registers
    #batt_charge = client.read_input_registers(1056, 2, slave=1).registers
    client.close()
    inv1 = results[0] << 16 | results[1]
    # int is close enough precision for my purposes
    print(f"Local load today: {int(inv1/10)}")
    return int(inv1/10)

def get_shortfall():
    # How much power in kwh do we need tomorrow?
    # Look at current usage over today to get an indication of average usage
    daily_kwh_required = get_lifetime_average_daily_load() # get_local_load_today()
    print(f"Daily kWh required: {daily_kwh_required}")
    # How much of that is solar?
    solar_production_tomorrow = get_forecast_solar_prediction()
    print(f"kWh from solar tomorrow: {solar_production_tomorrow}")
    # How much battery do we need to fill in?
    power_shortfall = daily_kwh_required - solar_production_tomorrow
    print(f"Power shortfall: {power_shortfall}")
    return power_shortfall
    # if power_shortfall < 0:
    #     print("We have enough solar for tomorrow")
    #     batt_percent_soc_needed_for_tomorrow = 0
    # else:
    #     print("We need to use the battery tomorrow")
    #     power_shortfall = abs(power_shortfall)
    #     batt_size = get_battery_size()
    #     print(f"Battery size: {batt_size}")
    #     batt_percent_soc_needed_for_tomorrow = ((power_shortfall * 1.1 / batt_size) * 100) + 10 # 10% deadzone and 10% buffer.  This will need tweaking
    # print(f"Battery SOC needed for tomorrow: {batt_percent_soc_needed_for_tomorrow}")
    # return math.ceil(batt_percent_soc_needed_for_tomorrow)

def get_current_battery_charge():
    # Battery state of charge s held in register 1014
    return 0
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    results = client.read_input_registers(1014, 1, slave=1)
    client.close()
    soc = results.registers[0]
    battery_kwh = 13 / 100 * soc
    print(f"Current battery kwh: {battery_kwh}")


slots_dict = plan()
calculation_dict  = calculation(slots_dict)
execute_dict = execute(calculation_dict)



