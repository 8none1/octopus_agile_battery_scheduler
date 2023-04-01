#!/bin/env python3

# Goal: find the right time to charge the battery.
# The battery takes about 4 hours to charge from 10% to 100%.
# Look for the cheapest 2 hour and 4 hour windows
# We want to hit mid night with at least 30% charge
# The battery has 6 time slots available.
# Would be useful to know the current gas price to make hot water when electricity is cheaper than gas.
# Would be useful to know when how much cheaper the agile prices are than the standard variable tariff.
# Maybe just control the inverter directly rather than using the time slots




### TODO:  What we really need is a list of the cheapest slots: 30m slots up to 4 hours, 2 hours slots (cheapest 2) four hour slot.  Perhaps before overnight and during the day.
#          put that in one big list with a duration.  Then you can work out how much duration you need and get the cheapest slot for that duration.
#             - Get the 8 cheapest 30m slots
#             - Get the 2 cheapest 4 hour slots
#             - Get the 4 cheapest 2 hour slots
#             - Get the 2 cheapest rolling 2 hour slots
#             - During day time and during night time
# I need to be this amount charged by this time.
# I want to charge in continuous slots or I'm happy with bursts.
# TODO: Add linear regression for battery SOC to try and predict when the battery will be exhausted.
# TODO: Move integral calculations out of flux and in to a separate script.



import sys
import requests
import pandas as pd
import datetime
import pytz
from argparse import ArgumentParser
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
import math

try:
    from pymodbus.client import ModbusTcpClient
    MODBUS = True
except:
    print("If you want to control your inverter with this script you need to install pymodbus")
    MODBUS = False

import api_key # Create a file called "api_key.py" and put your API key in it.  See api_key.py.example for an example.

__version__ = "0.1"

max_ac_charge_rate = 2.7 # kW
inverter_addr = 'ew11-1'
battery_size = None # 13 # kWh
# cheap = 15 # p/kWh anything below this is cheap.
# Get gas price from Octopus API.  If electricity is cheaper than gas then use electricity to heat water.
prices = None
start_time = None
end_time = None
idle_batt_usage = 5 # percent battery used per hour while house is idle
gas_price = 10.31 # p/kWh TODO: Look this up from the API


class Prices:
    def __init__(self, start_time = datetime.datetime.now().isoformat()+"Z", end_time = None, cheap=15, dummy=False):
        # TODO: move the product code etc to either a config file or a command line argument, or pull it from the API
        base_url = "https://api.octopus.energy/v1/"
        product_code = "AGILE-FLEX-22-11-25"
        tariff_code = "E-1R-AGILE-FLEX-22-11-25-A" # https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25
        agile_price_url = base_url + "products/" + product_code + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/"
        agile_price_url += "?period_from=" + start_time
        if end_time is not None:
            agile_price_url += "&period_to=" + end_time.isoformat() + "Z"
        print("URL: " + agile_price_url)
        r = requests.get(agile_price_url)
        self.prices_dict = r.json()
        self.two_hour_windows = None
        self.four_hour_windows = None
        self.cheapest_30min_slots = None
        self.economy_slots = None
        self.cheap = cheap
        self.dummy = dummy
        self.build_dataframe()
    
    def build_dataframe(self):
        start_time    = pd.DatetimeIndex(x['valid_from'] for x in self.prices_dict['results'])
        end_time      = pd.DatetimeIndex(x['valid_to'] for x in self.prices_dict['results'])
        value_inc_vat = [x['value_inc_vat'] for x in self.prices_dict['results']]
        self.prices = pd.DataFrame({'start_time':start_time, 'end_time': end_time, 'value_inc_vat': value_inc_vat})
        self.prices.sort_values(by="start_time", inplace=True)
        self.min_price = self.prices[self.prices.value_inc_vat == self.prices.value_inc_vat.min()] # Keep it as a frame to keep the start and end times
        self.max_price = self.prices[self.prices.value_inc_vat == self.prices.value_inc_vat.max()]
        self.avg_price = self.prices.mean(numeric_only=True).values[0]
        print("\n")
        print(f"Min price: {self.min_price.head(1).value_inc_vat.values[0]:.2f}p/kWh \t{self.min_price.head(1).start_time.values[0]} to {self.min_price.head(1).end_time.values[0]}")
        print(f"Max price: {self.max_price.head(1).value_inc_vat.values[0]:.2f}p/kWh \t{self.max_price.head(1).start_time.values[0]} to {self.max_price.head(1).end_time.values[0]}")
        print(f"Avg price: {self.avg_price:.2f}p/kWh")
        print("\n")
        self.get_two_hour_windows()
        self.get_four_hour_windows()
        self.get_cheapest_30min_slots()
        print(f"Cheapest 2 hour window: {self.two_hour_windows.head(1).value_inc_vat.values[0]:.2f}p/kWh \t{self.two_hour_windows.head(1).start_time.values[0]} to {self.two_hour_windows.head(1).end_time.values[0]}")
        print(f"Cheapest 4 hour window: {self.four_hour_windows.head(1).value_inc_vat.values[0]:.2f}p/kWh \t{self.four_hour_windows.head(1).start_time.values[0]} to {self.four_hour_windows.head(1).end_time.values[0]}")
        print("\n")

    def get_min_price(self):
        return self.min_price.iloc[0]['value_inc_vat']
    def get_max_price(self):
        return self.max_price.iloc[0]['value_inc_vat']
    def get_avg_price(self):
        return self.avg_price
    
    def get_two_hour_windows(self):
        # This finds a contiguous 2 hour window that is the cheapest.
        if self.two_hour_windows is not None:
            return self.two_hour_windows
        two_hour_windows = self.prices.rolling('2h', min_periods=4, on='start_time').mean()
        two_hour_windows.dropna(inplace=True)
        two_hour_windows.sort_values(by='value_inc_vat', inplace=True)
        two_hour_windows.drop(two_hour_windows[two_hour_windows.value_inc_vat > self.avg_price].index, inplace=True)
        two_hour_windows = remove_overlap(two_hour_windows, pd.Timedelta('1h30m'))
        two_hour_windows = add_window_bounds(two_hour_windows, pd.Timedelta('1h30m'))
        self.two_hour_windows = two_hour_windows
        return self.two_hour_windows
    
    def get_four_hour_windows(self):
        # This finds a contiguous 4 hour window that is the cheapest.
        if self.four_hour_windows is not None:
            return self.four_hour_windows
        four_hour_windows = self.prices.rolling('4h', min_periods=8, on='start_time').mean()
        four_hour_windows.dropna(inplace=True)
        four_hour_windows.sort_values(by='value_inc_vat', inplace=True)
        four_hour_windows.drop(four_hour_windows[four_hour_windows.value_inc_vat > self.avg_price].index, inplace=True)
        four_hour_windows = remove_overlap(four_hour_windows, pd.Timedelta('3h30m'))
        four_hour_windows = add_window_bounds(four_hour_windows, pd.Timedelta('3h30m'))
        self.four_hour_windows = four_hour_windows
        # If the average 4 hour unit price is lower than "cheap" then reset cheap to be the average 4 hour unit price.
        #if four_hour_windows.value_inc_vat.mean() < self.cheap:
        self.cheap = four_hour_windows.value_inc_vat.mean()
        return self.four_hour_windows
    
    def get_cheapest_30min_slots(self):
        # This finds 30 min slots that are cheaper than the average 4 hour unit price.
        if self.cheapest_30min_slots is not None:
            return self.cheapest_30min_slots
        cheapest_30min_slots = self.prices.sort_values(by="value_inc_vat").drop(self.prices[self.prices.value_inc_vat > self.cheap].index)
        # This self-adjusting cheap price is a bit risky I think. e.g. what if we have two negative slots in a row, it could throw the average. 
        #  We'll have to see how it goes.  See the four hour window section for how it's calculated.
        self.cheapest_30min_slots = cheapest_30min_slots
        return self.cheapest_30min_slots
    
    def get_cheapest_n_slots(self, num_slots):
        # This finds the cheapest 2 hour spread of slots.
        slots = self.cheapest_30min_slots
        slots.sort_values(by="value_inc_vat", inplace=True)
        slots = slots.head(num_slots)
        slots = slots.reset_index(drop=True)
        return slots
    
    def get_economy_slots(self, start_time=datetime.datetime.utcnow().replace(tzinfo=pytz.utc), end_time=None, max_slots=48):
        # The goal of this function is to return a dataframe of the cheapest slots between 19:00 and 07:00
        # i.e. how can we charge the battery before tomorrow morning?
        max_slots = int(max_slots)
        print(f"Start time: {start_time}")
        if end_time is None:
            end_time = start_time + datetime.timedelta(days=1)
        print(f"End time: {end_time}")
        cheap_30min_slots = self.prices.sort_values(by="value_inc_vat").drop(self.prices[self.prices.value_inc_vat > self.cheap].index)
        self.cheap_30min_slots = cheap_30min_slots
        if cheap_30min_slots.empty:
            print("Error: No cheap slots found.\nThis means that the cheapest four hour slot found was the cheapest overall slot.")
            return cheap_30min_slots# Maybe return the 4 hour slot here?  Perhaps better to catch an empty list in the calling function.
        index = pd.DatetimeIndex(cheap_30min_slots.start_time)
        #economy_slots = cheap_30min_slots.iloc[index.indexer_between_time(between_start_time, between_end_time)].sort_values(by="start_time").head(max_slots)
        # Sort by cost so that we actually get the cheapest slots first
        #economy_slots = cheap_30min_slots.iloc[index.indexer_between_time(between_start_time, between_end_time)].sort_values(by="value_inc_vat").head(max_slots)
        mask = (cheap_30min_slots['start_time'] >= start_time) & (cheap_30min_slots['start_time'] <= end_time)
        economy_slots = cheap_30min_slots.loc[mask].sort_values(by="value_inc_vat").head(max_slots)
        economy_slots.sort_values(by="start_time", inplace=True)
        economy_slots.reset_index(drop=True, inplace=True)
        #economy_slots['grp_time'] = economy_slots.end_time.diff().dt.seconds.gt(1800).cumsum()
        #economy_slots = economy_slots.groupby('grp_time').agg({'start_time': 'min', 'end_time': 'max', 'value_inc_vat': 'mean'})
        #print(f"Economy slots: {economy_slots}")
        #economy_slots.reset_index(drop=True, inplace=True)
        #economy_slots['grp_time'] = economy_slots.end_time.diff().dt.seconds.gt(3600).cumsum()
        #economy_slots = economy_slots.groupby('grp_time').agg({'start_time': 'min', 'end_time': 'max', 'value_inc_vat': 'mean'})
        #economy_slots.reset_index(drop=True, inplace=True)
        self.economy_slots = economy_slots
        return economy_slots
    
    def write_to_influxdb(self, dummy=False):
        if dummy: return False
        # You need the index to be a time column otherwise InfluxDB will not accept it. (e.g. index "0" = epoch zero = 1970-01-01 00:00:00 = a long time ago = outside the RP of the bucket)
        influx_df = self.prices.set_index('start_time')
        with InfluxDBClient(url=api_key.influxdb_url, token=api_key.influxdb_token, org=api_key.influxdb_org) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=api_key.influxdb_bucket, record=influx_df, data_frame_measurement_name='agile_prices')
        print("Prices written to InfluxDB")

def merge_slots(slots):
    # This merges slots that are contiguous. It means that we use fewer programming slots on the inverter.
    # Each slot must be the same duration.
    duration = slots.head(1).end_time - slots.head(1).start_time
    slots.sort_values(by="start_time", inplace=True)
    slots.reset_index(drop=True, inplace=True)
    slots['grp_time'] = slots.end_time.diff().dt.seconds.gt(duration.dt.seconds[0]).cumsum()    
    slots = slots.groupby('grp_time').agg({'start_time': 'min', 'end_time': 'max', 'value_inc_vat': 'mean'})
    slots = slots.reset_index(drop=True)
    return slots

def write_to_inverter(register, values_list, dummy=True):
    if MODBUS is True and dummy is False:
        client = ModbusTcpClient(inverter_addr)
        client.connect()
        client.write_registers(register, values_list, slave=1)
        client.close()
        return True
    else:
        print("Not actually writing to inverter")
    return False

def sync_inverter_time(dummy=True):
    system_now = datetime.datetime.utcnow() # Keep the inverter in UTC.  The Agile prices are all in UTC
    time_list = [system_now.year-2000, system_now.month, system_now.day, system_now.hour, system_now.minute, system_now.second]
    write_to_inverter(45, time_list, dummy=dummy)

def zero_charging_slots(dummy=True):
    write_to_inverter(1100, [0]*9, dummy)
    write_to_inverter(1018, [0]*9, dummy)

def get_battery_size():
    # I don't know if this works.  It seems to align with my set up, but I don't know if it's correct.
    print("Reading battery count")
    if not MODBUS:
        return False
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    results = client.read_input_registers(1110, 1, slave=1) # 1110 is the register for the number of battery modules
    client.close()
    return results.registers[0] * 6.5 # 6.5kWh per battery module

def get_battery_soc():
    # TODO:  Move all inverter functions to a class. This function should be a method of that class.
    # Stop calling modbus multiple times for the same thing
    if not MODBUS:
        return False
    # Battery state of charge s held in register 1014
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    results = client.read_input_registers(1014, 1, slave=1)
    client.close()
    return results.registers[0]

def get_current_charging_slots():
    if not MODBUS:
        return False
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    charging_slots = []
    charging_slots.extend(client.read_holding_registers(1100, 9, slave=1).registers)
    charging_slots.extend(client.read_holding_registers(1018, 9, slave=1).registers) # Looks like the docs are wrong here. 1018 is the start of the charging slots not 1017 
    charge_limit = client.read_holding_registers(1091, 1, slave=1).registers[0]
    ac_charge_enabled = client.read_holding_registers(1092, 1, slave=1).registers[0]
    results = client.read_holding_registers(45, 7, slave=1)
    year, month, day, hour, minute, second, dow = results.registers
    inverter_now = datetime.datetime(year, month, day, hour, minute, second)
    client.close()

    charge_slots_list = []
    for i in range(0, len(charging_slots), 3):
        start_time = datetime.time(charging_slots[i] >> 8, charging_slots[i] & 255)
        end_time = datetime.time(charging_slots[i+1] >> 8, charging_slots[i+1] & 255)
        enabled = charging_slots[i+2]
        charge_slots_list.append([start_time, end_time, enabled])

    for each in charge_slots_list:
        print(f"Slot: {each[0]} - {each[1]} Enabled: {each[2]}")

    print(f"Charge Limit: {charge_limit}")
    print(f"AC Charge Enabled: {ac_charge_enabled}")
    print(f"Inverter time: {inverter_now}")

def set_charging(slots, dummy=True):
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
    sync_inverter_time(dummy)
    zero_charging_slots(dummy)
    a,b = [],[]
    for slot in charging_slots_list[0:3]:
        a.extend(slot)
    for slot in charging_slots_list[3:6]:
        b.extend(slot)
    print(a)
    print(b)
    write_to_inverter(1100, a, dummy)
    write_to_inverter(1018, b, dummy)

def set_max_soc(soc):
    print(f"Setting max SOC to {soc}%")
    write_to_inverter(1091, [soc])

def convert_to_local_timezone(slots):
    local_tz = pytz.timezone("Europe/London")
    slots["start_time"] = slots["start_time"].dt.tz_convert(local_tz)
    slots["end_time"]   = slots["end_time"].dt.tz_convert(local_tz)
    return slots

def parse_args():
    parser = ArgumentParser(description="Control Growatt SPH inverters and batteries to charge the battery at the cheapest time possible using Agile Octopus.")
    programming_group = parser.add_argument_group("Charge Programming")
    programming_group.add_argument("-z", "--zero", dest="zero", help="Zero out the battery charging schedule", action="store_true")
    programming_group.add_argument("-d", "--duration", dest="duration", help="Set the duration of the charge in minutes.  Default is 240 (4 hours)", default=240, type=int)
    programming_group.add_argument("-st", "--start-time", dest="start_time", help="Set the earliest time to search for a slot for the charge.", type=datetime.datetime.fromisoformat)
    programming_group.add_argument("-et", "--end-time", dest="end_time", help="Set the latest time to search for a slot for the charge.  Default is now + 4 hours. YYYY-MM-DDTHH:MM:SS", type=datetime.datetime.fromisoformat)
    
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("-e", "--economy", dest="economy", help="Program the cheapest over-night charging schedule possible", action="store_true")
    mode_group.add_argument("-4", "--4hour", dest="fourhour", help="Program the cheapest 4 hour charging schedule possible", action="store_true")
    mode_group.add_argument("-2", "--2hour", dest="twohour", help="Program the cheapest 2 hour charging schedule possible", action="store_true")
    mode_group.add_argument("-a", "--auto", dest="auto", help="Program the cheapest charging schedule possible taking in to account solar conditions and current soc", action="store_true")

    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument("-c", "--cheap", dest="cheap", help="Set the threshold for cheap electricity in p/kWh.  Default is 15.0", type=float)
    config_group.add_argument("-i", "--inverter", dest="inverter", help="Set the inverter address.  Default is ew11-1", default='ew11-1')
    config_group.add_argument("-b", "--battery", dest="battery", help="Forcibly set the battery size in kWh.", default=None, type=int)
    config_group.add_argument("-r", "--rate", dest="rate", help="Set the maximum AC charge rate in kW.  Default is 100%%", default=100, type=int)
    #config_group.add_argument("-D", "--debug", dest="debug", help="Enable debug output", action="store_true")
    config_group.add_argument("--dummy", dest="dummy", help="Dummy  run. Don't actually program the inverter", action="store_true")
    config_group.add_argument("-t", "--time", dest="time", help="Set the time on the inverter", action="store_true")

    info_group = parser.add_argument_group("Information")
    info_group.add_argument("-v", "--version", dest="version", help="Print version information", action="version", version="%(prog)s " + __version__)
    info_group.add_argument("-C", "--soc", dest="soc", help="Return the state of charge of the battery in %% or set the max. SOC", type=int, default=None, nargs="?")
    info_group.add_argument("-S", "--schedule", dest="schedule", help="Return the current charging schedule", action="store_true")
    info_group.add_argument("-P", "--prices", dest="prices", help="Return the current Agile prices", action="store_true")
    info_group.add_argument("-I", "--influx", dest="influx", help="Write the current prices to InfluxDB", action="store_true")

    args = parser.parse_args()
    print(args)
    return args


def start_of_next_period():
    # Return the datetime of today at 11pm
    # Todo: deal with clock changes
    return datetime.datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)

def remove_overlap(window, window_length):
    # Window is a DataFrame of start times
    # Window length is how long the windows are
    # Window end is always 30m later that the start tine in the window because Agile slots are 30mins long and the timestamp is the start of the last 30m period.
    # window_length needs to be a pandas Timedelta object
    # Iterate through the windows and drop any overlapping windows.  We are sorted by price
    # so the earlier window should be cheapest and so kept.
    # From the docs: You should never modify something you are iterating over.
    if type(window) != pd.core.frame.DataFrame:
        print("ERROR: Window is not a DataFrame")
        raise TypeError
    temp_frame = window.copy()
    for i1 in window.itertuples():
        window_interval = pd.Interval(i1.start_time - window_length, i1.start_time + pd.Timedelta('30m'))
        for i2 in window.itertuples():
            if i1.Index == i2.Index:
                continue
            wi2 = pd.Interval(i2.start_time - window_length, i2.start_time + pd.Timedelta('30m'))
            if window_interval.overlaps(wi2):
                if i2.value_inc_vat > i1.value_inc_vat:
                    temp_frame.drop(i2.Index, inplace=True, errors='ignore')
    return temp_frame

def add_window_bounds(window, window_length):
    # This creates a whole new frame, we could probably just update the existing one
    # but I found this tricky to do.  This is easier to understand and really doesn't
    # need optimising as it's a small amount of data.
    start_time_list = []
    end_time_list   = []
    values_list     = []
    
    for each in window.itertuples():
        start_time = each.start_time - window_length
        end_time = each.start_time + pd.Timedelta('30m') 
        start_time_list.append(start_time)
        end_time_list.append(end_time)
        values_list.append(each.value_inc_vat)
    df = pd.DataFrame({'start_time':start_time_list, 'end_time': end_time_list, 'value_inc_vat': values_list})
    return df

def get_solar_production_tomorrow(dummy=True):
    url = "https://api.forecast.solar/estimate/watthours/day/52.1322466021396/-0.21998598515728754/27/-80/6.720"
    # Might change this to use the per-hour data.  Then we can see how much solar is left for the day.
    # That might mean signing up for an account, then we can hit the API once a minute if we really want to
    headers = {"Accept": "application/json"}
    r = requests.get(url, headers=headers)
    wh = r.json()['result'][(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')]
    return wh / 1000

def auto_charge(prices, dummy):
    global battery_size
    # We are going to switch the inverter in to battery first mode in order to charge the battery.
    # We could switch *out* of battery first mode as soon as the battery is charge, but that we are charging means that
    # the electricity is at its cheapest.  So... I propose that we don't switch out of battery first mode until the time
    # slot is up.  i.e. consume from the grid for the entire slot.  This also allows us to run heavy loads e.g. the washing
    # machine, dishwasher, tumble dryer, etc from the grid, and so not consuming the battery.
    # We can limit the amount of power we draw from the grid to charge the battery by simply setting the maximum SOC.
    # To start with there will be two possible options: 100% or 50%.  This function will try and decide which by simply
    # looking at solar production tomorrow and seeing what's left after the house has used it's usual amount.
    # We can also assume that we need to charge overnight. We can rule out slots which are during the day. This might not be true all the time, but
    # will worry about that later.
    # TODO:  Work out how long after sunrise we can start generating 600W+  For now hard code to 8am
    # TODO: deal with import being cheaper than export.  i.e. charge the battery to 100% regardless, and keep in batt first mode for the duration of the slots.
    current_soc = get_battery_soc() # test
    tomorrow_solar = 11# get_solar_production_tomorrow() # test
    typical_usage = 14.0 # kWh
    if battery_size is None:
        battery_size = get_battery_size()
    # We need 25% of the battery to get through the night. 00:00 to 08:00
    print(f"Tomorrow's solar production is {tomorrow_solar} kWh")
    print(f"Typical usage is {typical_usage} kWh")
    spare_solar = tomorrow_solar - typical_usage
    if spare_solar < 0: spare_solar = 0
    max_additional_charge = spare_solar / battery_size * 100
    print(f"Leaving {spare_solar} kWh to top up the battery")
    print(f"Battery capacity is: {battery_size} kWh")
    print(f"Which means we can add max. {max_additional_charge}% to the battery tomorrow.")
    
    required_charge_percent = 100 - max_additional_charge
    if required_charge_percent < 0: required_charge_percent = 0
    required_charge_kw = (battery_size / 100) * required_charge_percent
    required_charge_time = int(round((required_charge_kw / 2.7) * 2) / 2) # hours
    print(f"Required charge is {required_charge_percent}%")
    print(f"Required charge is {required_charge_kw} kWh")
    print(f"Required charge time is {required_charge_time} hours")
    print(f"Current battery SOC is {current_soc}%")

    now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    print(f"Now is {now}")
    if now.hour <= 23:
        tomorrow_8am = now + datetime.timedelta(days=1)
    else:
        tomorrow_8am = now

    tomorrow_8am = tomorrow_8am.replace(hour=8, minute=0, second=0, microsecond=0)
    print(f"Tomorrow 8am is {tomorrow_8am}")
    
    hours_to_useable_solar = round((((tomorrow_8am - now).total_seconds() / 3600) + 0.5) * 2) / 2
    print(f"Hours_to_useable_solar: {hours_to_useable_solar}")
    # How much battery % per hour?
    battery_percent_per_hour_available = (current_soc-10) / hours_to_useable_solar # Last 10% is unusable
    print(f"How much battery % can we use per hour until we have solar again?: {battery_percent_per_hour_available}")
    # TODO:  It would be useful if we can say that this script isn't run until solar is low or zero.  Then we can assume that
    # the battery won't get any more charge for the rest of the day.  Then we can make predictions about when the battery will run out.
    battery_run_time_remaining = (current_soc - 10) / 5 # 5% per hour.  Might minus a higher number to add a safety margin
    print(f"Battery run time remaining: {battery_run_time_remaining} hours")


    if battery_run_time_remaining > hours_to_useable_solar and required_charge_percent == 0:
        print("The battery will last until sunrise, and there will be enough solar tomorrow to charge.  Don't need to charge tonight.")
        # TODO: If there is a period of very cheap electricity (less than the export price perhaps, negative, etc) then charge the battery during those slots anyway.
        # TODO: If the electricity is cheaper than gas, also turn on the immersion.
        return False
    
    elif required_charge_percent > 0: # TODO Need to better understand what number should go here
        # Do we care if the battery runs out before the cheapest charging time?  Probably not actually.
        # We could do, and that will complicate things a bit, but it is a possibility.  Just need to look for charging slots that are earlier than the battery run out time.
        # The downside is that we might miss out on the cheapest charging slots.
        # What we do need to do though is adjust the charging level to account for the time between the end of the cheap charging slot and sunrise o'clock.
        slots = prices.get_economy_slots(max_slots=(required_charge_time*2),end_time=tomorrow_8am)
        print(f"Slots:\n{slots}")
        end_of_charge = slots.tail(1)['end_time'].item()
        print(f"End of charge: {end_of_charge}")
        hours_from_end_of_charge_until_sunrise = (tomorrow_8am - end_of_charge).total_seconds() / 3600
        print(f"Hours from end of charge until sunrise: {hours_from_end_of_charge_until_sunrise}")
        # How much battery % will this take?
        additional_batt_percent_needed = hours_from_end_of_charge_until_sunrise * 5
        additional_kw_needed = (battery_size / 100) * additional_batt_percent_needed
        print(f"Additional kw needed: {additional_kw_needed}")
        # How much charge time will this take?
        additional_charge_time = round((additional_kw_needed / 2.7) * 2) / 2 # hours
        print(f"Additional charge time: {additional_charge_time}")
        extra_slots = prices.get_economy_slots(max_slots=(additional_charge_time*2),start_time=end_of_charge)
        print(f"Extra slots:\n{extra_slots}")
        average_price = extra_slots['value_inc_vat'].mean()
        print(f"Average price of extra slots: {average_price}")
        min_price = prices.get_min_price()
        print(f"Lowest unit cost available now: {min_price}")
        if average_price < (min_price * 1.1):
            print(f"Cheapest price: {prices.min_price.values[0]}")
            print("Average price of extra slots is within 10% of the cheapest price.  Adding extra slots.")
            slots = slots.append(extra_slots)
            slots = slots.sort_values(by='start_time')
        else:
            print("Average price of extra slots is not within 10% of the cheapest price.  Not adding extra slots.")
        
        print(f"Final auto slots are:\n{slots}")
        slots = merge_slots(slots)
        print(f"Final auto slots after merge:\n{slots}")

            #print(f"New slots:\n{slots}")


    # TODO: Always charge when power is super cheap (lower than export cost minus a bit?)        
    total_duration_of_slots = slots.end_time.max() - slots.start_time.min() # .total_seconds() / 3600
    print(f"Total duration of slots: {total_duration_of_slots}")
    set_charging(slots, dummy)

    


   
 
        
    #     start_time = datetime.datetime.utcnow().strftime("%H:%M")
    #     slots = prices.get_economy_slots(max_slots=(hours_needed_to_get_to_required_charge*2),end_time=datetime.datetime(now.year, now.month, now.day+1, 8, 0, 0, 0, tzinfo=pytz.utc))
    #     print(f"Slots:\n{slots}")
    #     end_of_charge = slots.tail(1)['end_time'].item()
    #     print(f"End of charge: {end_of_charge}")
    #     hours_from_end_of_charge_until_sunrise = (tomorrow_8am - end_of_charge).total_seconds() / 3600
    #     print(f"Time from end of charge until sunrise: {hours_from_end_of_charge_until_sunrise}")
    #     # How much battery % will this take?
    #     additional_batt_percent_needed = (hours_from_end_of_charge_until_sunrise * 5)
    #     print(f"Battery from end of charge until sunrise: {additional_batt_percent_needed}")
    #     #total_duration_of_slots = slots.max()-slots.min().total_seconds() / 3600
    #     #print(f"Total duration of slots: {total_duration_of_slots}")


    # else:
    #     # Assume we will need a 2 hour slot to charge the battery
    #     two_hour = prices.get_two_hour_windows().head(1)
    #     separate_windows = prices.get_cheapest_n_slots(6)
    #     separate_windows = merge_slots(separate_windows)
    #     two_hour_cost = two_hour.value_inc_vat.mean()
    #     separate_cost = separate_windows.value_inc_vat.mean()
    #     print(f"Two hour cost: {two_hour_cost}")
    #     print(f"Separate cost: {separate_cost}")



def main():
    #global prices
    #global start_time
    #global end_time
    global battery_size


    prices = None
    args = parse_args()
    print(args)
    if args.inverter:
        inverter_addr = args.inverter
    if args.zero:
        zero_charging_slots(args.dummy)
    # if args.cheap:
    #     global cheap
    #     cheap = args.cheap
    if args.schedule:
        get_current_charging_slots()
    if args.time:
        sync_inverter_time(args.dummy)
        print("Inverter time set")
    if args.start_time:
        start_time = args.start_time
        if not args.end_time:
            end_time = start_time + datetime.timedelta(hours=4)
    if args.end_time:
        end_time = args.end_time
        if not args.start_time:
            start_time = end_time - datetime.timedelta(hours=4)
    if not args.start_time and not args.end_time:
        start_time = datetime.datetime.now()
    if args.soc is None:
        print(f"Current battery charge: {get_battery_soc()}%")
    elif args.soc > 0:
        print("Setting max SOC")
        set_max_soc(args.soc)
    if args.battery: battery_size = args.battery
    if args.economy:
        if prices is None:
            prices = Prices()
        set_charging(prices.get_economy_slots(), args.dummy)
        # set_economy_charging(prices)
    if args.fourhour:
        if prices is None:
            prices = Prices()
        set_charging(prices.get_four_hour_windows().head(1), args.dummy)
    if args.twohour:
        if prices is None:
            prices = Prices()
        set_charging(prices.get_two_hour_windows().head(1), args.dummy)
    if args.auto:
        if prices is None:
            prices = Prices()
        auto_charge(prices, args.dummy)
    if args.influx:
        if prices is None:
            prices = Prices()
        prices.write_to_influxdb(args.dummy)
    if args.prices:
        if prices is None:
            prices = Prices()
        print("All prices in LOCAL time:")
        print(prices.prices.to_markdown())
        print("\nCheapest combined TWO HOUR slots in LOCAL time:")
        print(convert_to_local_timezone(prices.get_two_hour_windows()).to_markdown())
        print("\nCheapest combined FOUR HOUR slots in LOCAL time:")
        print(convert_to_local_timezone(prices.get_four_hour_windows()).to_markdown())
        print("\nCheapest ECONOMY slots in LOCAL time:")
        if prices.get_economy_slots().empty:
            print("No economy slots found.  Use the four hour slot instead")
        else:
            print(convert_to_local_timezone(prices.get_economy_slots()).to_markdown())
    sys.exit()


if __name__ == "__main__":
    main()





# Now we have:
# - Cheapest 2 hour consecutive slots
# - Cheapest 4 hour consecutive slots
# - Cheapest 30 min slots
#
# We could add the cheapest 2 hour NON consecutive slots
# and the cheapest 4 hour NON consecutive slots

# The "auto" program might like to:
# - If using the non consecutive slots to charge, then find if there are actually consecutive slots so that we can collapse them in to one single charging period and therefore save a charging slot on the inverter
# - Remove anything later than the time at which this will run (likely 6pm ish) because those will be recalculated tomorrow
# - Remove anything earlier than the 4 or 2 hour bulk slot. If we're going to do a full charge we should try and shift the bulk of the cost to the cheapest slot
# - 

# Get solar prediction for the next 24 hours:  https://api.forecast.solar/estimate/watthours/day/52.1322466021396/-0.21998598515728754/27/-80/6.720
# Can deliver JSON if the "accept" type is set. 


# Strategy:
#  Always charge the battery when the cost is lower than "cheap""
#  Aim for contiguous periods of charging where possible
#  Don't miss out on super cheap periods of charging.  The most the battery can charge during 30mins is 4kW * 30 mins = 2kWh which is about 12.5% of the battery capacity
# Wrong. The battery can only charge from AC at a max rate of 2.7kWh it seems.
#  Call it 10% to be safe

# We should read the battery state at the start of the periods and then decide whether to charge or not?
# Probably not since if the electricity is cheap enough to charge the battery then it's probably cheap enough to use the electricity too and save the battery for later.


# When do we need power?
# - During peak times
# - During the night
# - During the day when the solar is low
#
# When do we want to charge the battery?
# - During the day when the solar is high
# - When electricity is cheap
#
# - Do we always want to charge when electricity is cheap?
#  - Yes. This will switch the house to using grid power too so might save a little bit of wear on the battery?
# - How do we achieve this?
#  - Try and use the slots on the inverter, condense the slots if possible, if not run the script a few times a day and create the slots on the fly?
#
# - Need to find the current state of charge of the battery
# - Aim to have 80%+ by 4pm?


# Day charging strategy:
# Aim for 75%+ by 4pm if solar generation is low

# Write numbers to influxdb?  Only once a day though.  Don't need to write every time the script runs.


# Charge planner
# - Read current state of charge
# - Read current solar generation/time
# If night and trending towards zero, find somewhere to charge
# If tomorrows solar generation is high, charge to enough to get to morning with some spare. 
# If tomorrows solar generation is low, charge to full over night if cheap.  Or if cheaper than tomorrow.
# Trend towards zero 

