#!/usr/bin/env python3

import sys
import requests
import pandas as pd
import datetime
import pytz
from argparse import ArgumentParser
import math

try:
    from pymodbus.client import ModbusTcpClient
    MODBUS = True
except:
    print("If you want to control your inverter with this script you need to install pymodbus")
    MODBUS = False

__version__ = '0.0.1'
POWER_RESERVE_IN_CASE_OF_POWERCUT_HOURS = 2
BATTERY_CHARGE_RATE = 2.7 # kW/h
BATTERY_CAPACITY = 13 # kWh
INVERTER_ADDR = "ew11-1"

def get_current_battery_charge():
    if not MODBUS:
        return False
    client = ModbusTcpClient(INVERTER_ADDR)
    client.connect()
    results = client.read_input_registers(1014, 1, slave=1)
    client.close()
    soc = results.registers[0]
    battery_kwh = 13 / 100 * soc
    return battery_kwh


def get_forecast_solar_prediction():
    #return 3.723
    url = "https://api.forecast.solar/estimate/watthours/day/52.1322466021396/-0.21998598515728754/27/-80/6.720"
    # Might change this to use the per-hour data.  Then we can see how much solar is left for the day.
    # That might mean signing up for an account, then we can hit the API once a minute if we really want to
    headers = {"Accept": "application/json"}
    r = requests.get(url, headers=headers)
    j = r.json()
    if not j["result"]:
        print("Problem fetching the solar prediction")
        print(r.text)
        raise Exception("Solar problem")
    wh = j['result'][(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')]
    return wh / 1000


def actually_get_prices_from_octopus(start_time, end_time):
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
        return prices_dict
    else:
        raise Exception(
            f"Failed to fetch from Octopus with this complaint: {r.text}")


def plan(electricity_provider_fn=actually_get_prices_from_octopus,
         get_forecast_fn=get_forecast_solar_prediction,
         get_battery_charge_fn=get_current_battery_charge):
    # Get the prices from Octopus
    electricity_prices_slots = get_prices_from_octopus(electricity_provider_fn=electricity_provider_fn) # returns a pandas dataframe
    slots_dict = {'prices': electricity_prices_slots}
    slots_dict['daily_load'] = get_lifetime_average_daily_load()
    slots_dict['shortfall'] = get_shortfall(get_forecast_fn=get_forecast_fn, avg_load=slots_dict['daily_load'])
    slots_dict['battery_kwh_remaining'] = get_battery_charge_fn()
    return slots_dict

def calculation(slots_dict):
    electricity_prices_slots = slots_dict['prices']
    shortfall                = slots_dict['shortfall']
    battery_kwh_remaining    = slots_dict['battery_kwh_remaining']
    daily_load               = slots_dict['daily_load']

    print(f"Shortfall: {shortfall}")
    print(f"Current battery charge: {battery_kwh_remaining} kWh")
    print(f"Daily load: {daily_load}")

    
    buffer_kwh = POWER_RESERVE_IN_CASE_OF_POWERCUT_HOURS / 24 * daily_load # 2 hours of buffer.
    power_needed = (shortfall + buffer_kwh) - battery_kwh_remaining
    slots_needed = math.ceil(power_needed / (BATTERY_CHARGE_RATE / 2))
    print(f"Slots needed: {slots_needed}")

    if slots_needed > 0:
        battery_charge_slots = electricity_prices_slots.copy()
        battery_charge_slots.sort_values(by=['cost'], inplace=True)
        battery_charge_slots = battery_charge_slots.head(slots_needed)
        battery_charge_slots.sort_values(by=['start_time'], inplace=True)
        max_battery_charge_percent = math.ceil((power_needed / BATTERY_CAPACITY) * 100)
        print(f"Battery charge slots: {battery_charge_slots}")

    else:
        battery_charge_slots = None
        max_battery_charge_percent = None


    # TODO: Output a suitable dishwasher start time here

    calculation_dict = {'battery_charge_slots': battery_charge_slots, 'max_battery_charge_percent': max_battery_charge_percent, 'all_slots': electricity_prices_slots}
    return calculation_dict


def execute(calculation_dict):
    battery_charge_slots       = calculation_dict['battery_charge_slots']
    max_battery_charge_percent = calculation_dict['max_battery_charge_percent']
    all_slots                  = calculation_dict['all_slots']

    if battery_charge_slots is not None:
        print(f"Max battery charge percent: {max_battery_charge_percent}")
        print(f"Battery charge slots: {battery_charge_slots}")
        # Re-sort slots in to time order
        battery_charge_slots.sort_values(by=['start_time'], inplace=True)
        # Collapse slots where possible
        slot_duration = battery_charge_slots.head(1)['duration'].dt.seconds.values[0]
        battery_charge_slots['grp_time'] = battery_charge_slots.end_time.diff().dt.seconds.gt(slot_duration).cumsum()
        battery_charge_slots = battery_charge_slots.groupby('grp_time').agg({'start_time': 'min', 'end_time': 'max', 'cost': 'mean', 'duration': 'sum'})
        battery_charge_slots = battery_charge_slots.reset_index(drop=True)
        print(f"Collapsed battery charge slots:\n{battery_charge_slots}")
        # Set max charge percent (note: this may be an optimisation too far)
        ## Don't do this yet
        # Program inverter slots 0 - 5 leaving 6 free for HA
        set_charging(battery_charge_slots, dummy=False)

    else:
        print("No charging required")
        

def get_prices_from_octopus(start_time = None, end_time = None, electricity_provider_fn=actually_get_prices_from_octopus):
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

    prices_dict = electricity_provider_fn(start_time, end_time)
    start_time_list = pd.DatetimeIndex(x['valid_from'] for x in prices_dict['results'])
    end_time_list   = pd.DatetimeIndex(x['valid_to']   for x in prices_dict['results'])
    value_inc_vat   = [x['value_inc_vat']*10000 for x in prices_dict['results']]
    electricity_prices_slots = pd.DataFrame({'start_time':start_time_list, 'end_time': end_time_list, 'cost': value_inc_vat})
    electricity_prices_slots['duration'] = electricity_prices_slots.end_time - electricity_prices_slots.start_time
    electricity_prices_slots.sort_values(by=['start_time'], inplace=True)
    return electricity_prices_slots
    

def get_lifetime_average_daily_load():
    if not MODBUS:
        return 20
    client = ModbusTcpClient(INVERTER_ADDR)
    client.connect()
    runtime    = client.read_input_registers(57, 2, slave=1).registers
    total_load = client.read_input_registers(1062, 2, slave=1).registers
    client.close()
    runtime = ((runtime[0] << 16 | runtime[1]) / 2) / 60 / 60 # Reading is in 0.5 second increments.  Convert to hours.
    total_load = (total_load[0] << 16 | total_load[1]) / 10 # Reading is in 0.1kWh increments.  Convert to kWh.
    #print(f"Total inverter running time: {runtime} hours\nTotal load: {total_load} kWh")
    average_load = total_load / runtime # per hour
    average_load = average_load * 24
    #print(f"Average load per day: {average_load} kWh")
    return average_load

def get_local_load_today():
    if not MODBUS:
        return False
    client = ModbusTcpClient(INVERTER_ADDR)
    client.connect()
    results = client.read_input_registers(1060, 2, slave=1).registers
    #batt_charge = client.read_input_registers(1056, 2, slave=1).registers
    client.close()
    inv1 = results[0] << 16 | results[1]
    # int is close enough precision for my purposes
    print(f"Local load today: {int(inv1/10)}")
    return int(inv1/10)

def get_shortfall(get_forecast_fn=get_forecast_solar_prediction, avg_load=None):
    # How much power in kwh do we need tomorrow?
    # Look at current usage over today to get an indication of average usage
    if avg_load is None:
        daily_kwh_required = get_lifetime_average_daily_load() # get_local_load_today()
    else:
        daily_kwh_required = avg_load
    print(f"Daily kWh required: {daily_kwh_required}")
    # How much of that is solar?
    solar_production_tomorrow = get_forecast_fn()
    print(f"kWh from solar tomorrow: {solar_production_tomorrow}")
    # How much battery do we need to fill in?
    power_shortfall = daily_kwh_required - solar_production_tomorrow
    print(f"Power shortfall: {power_shortfall}")
    return power_shortfall

def set_charging(slots, dummy=True):
    # Accepts a dataframe of slots and encodes them in to the inverter format
    # There are slot 6 slots for charging, but slot 6 is reserved for HA, so we're going to have
    # to truncate the slots to 5.

    print("Setting charging")
    charging_slots_list = []

    for r in slots.itertuples():
        start_hour = int(r.start_time.strftime('%H'))
        start_minute = int(r.start_time.strftime('%M'))
        end_hour = int(r.end_time.strftime('%H'))
        end_minute = int(r.end_time.strftime('%M'))
        print(f"Charging from {start_hour}:{start_minute} to {end_hour}:{end_minute}")
        encoded_start_time = start_hour << 8 | start_minute
        encoded_end_time = end_hour << 8 | end_minute
        print(f"Encoded start time: {encoded_start_time}")
        print(f"Encoded end time: {encoded_end_time}")
        charging_slots_list.append([encoded_start_time, encoded_end_time, 1])
    sync_inverter_time()
    #zero_charging_slots(dummy)
    a,b = [],[]
    for slot in charging_slots_list[0:3]:
        a.extend(slot)
    for slot in charging_slots_list[3:5]: # Truncate to 5, not 6.  Slot 6 is reserved for HA
        b.extend(slot)
    print(a)
    print(b)
    if not dummy:
        write_to_inverter(1100, a)
        write_to_inverter(1018, b)

def set_max_soc(soc):
    if soc < 1:
        print(f"Invalid SOC: {soc}")
        return False
    if soc > 100:
        soc = 100
    print(f"Setting max SOC to {soc}%")
    write_to_inverter(1091, [soc])


def write_to_inverter(register, values_list):
    if MODBUS is True:
        client = ModbusTcpClient(INVERTER_ADDR)
        client.connect()
        client.write_registers(register, values_list, slave=1)
        client.close()
        return True
    else:
        print("No MODBUS - can't write to inverter")
    return False

def sync_inverter_time():
    system_now = datetime.datetime.utcnow() # Keep the inverter in UTC.  The Agile prices are all in UTC
    time_list = [system_now.year-2000, system_now.month, system_now.day, system_now.hour, system_now.minute, system_now.second]
    write_to_inverter(45, time_list)
    


if __name__ == "__main__":
    slots_dict = plan()
    calculation_dict  = calculation(slots_dict)
    execute_dict = execute(calculation_dict)



