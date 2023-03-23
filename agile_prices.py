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


import sys
import requests
import pandas as pd
import datetime
from argparse import ArgumentParser
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

try:
    from pymodbus.client import ModbusTcpClient
except:
    print("If you want to control your inverter with this script you need to install pymodbus")
    MODBUS = False

import api_key # If we need to use the authenticated API, then we need an API key.  Store it in this file instead of in here. Also store other secret things in here.

battery_size = 16 # kWh
max_ac_charge_rate = 2.7 # kW
inverter_addr = 'ew11-1'
cheap = 15 # p/kWh anything below this is cheap.
# Get gas price from Octopus API.  If electricity is cheaper than gas then use electricity to heat water.
prices = None
start_time = None
end_time = None




class Prices:
    def __init__(self):
        global start_time
        global end_time
        base_url = "https://api.octopus.energy/v1/"
        product_code = "AGILE-FLEX-22-11-25"
        tariff_code = "E-1R-AGILE-FLEX-22-11-25-A" # https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25
        agile_price_url = base_url + "products/" + product_code + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/"
        if start_time is not None:
            agile_price_url += "?period_from=" + start_time.isoformat() + "Z"
            #agile_price_url += "?period_from=" + datetime.datetime.now().isoformat() + "Z"
        if end_time is not None:
            agile_price_url += "&period_to=" + end_time.isoformat() + "Z"
        print("URL: " + agile_price_url)
        r = requests.get(agile_price_url)
        self.prices_dict = r.json()
        self.two_hour_windows = None
        self.four_hour_windows = None
        self.cheapest_30min_slots = None
        self.economy_slots = None
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
        print(f"Cheapest 2 hour window: {self.two_hour_windows.head(1).value_inc_vat.values[0]:.2f}p/kWh \t{self.two_hour_windows.head(1).start_time.values[0]} to {self.two_hour_windows.head(1).end_time.values[0]}")
        print(f"Cheapest 4 hour window: {self.four_hour_windows.head(1).value_inc_vat.values[0]:.2f}p/kWh \t{self.four_hour_windows.head(1).start_time.values[0]} to {self.four_hour_windows.head(1).end_time.values[0]}")
        print("\n")

    def get_two_hour_windows(self):
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
        global cheap
        if four_hour_windows.value_inc_vat.mean() < cheap:
            cheap = four_hour_windows.value_inc_vat.mean()
        return self.four_hour_windows
    def get_cheapest_30min_slots(self):
        if self.cheapest_30min_slots is not None:
            return self.cheapest_30min_slots
        # if self.four_hour_windows is None:
        #     self.get_four_hour_windows()
        cheapest_30min_slots = self.prices.sort_values(by="value_inc_vat").drop(self.prices[self.prices.value_inc_vat > cheap].index)
        #cheapest_30min_slots = remove_overlap(cheapest_30min_slots, pd.Timedelta('30m'))
        #cheapest_30min_slots = add_window_bounds(cheapest_30min_slots, pd.Timedelta('30m'))
        self.cheapest_30min_slots = cheapest_30min_slots
        return cheapest_30min_slots
    def get_economy_slots(self):
        if self.economy_slots is not None:
            return self.economy_slots
        if self.cheapest_30min_slots is None:
            self.get_cheapest_30min_slots()
        index = pd.DatetimeIndex(self.cheapest_30min_slots.start_time)
        economy_slots = self.cheapest_30min_slots.iloc[index.indexer_between_time('19:00', '07:00')].sort_values(by="start_time")
        economy_slots.sort_values(by="start_time", inplace=True)
        economy_slots.reset_index(drop=True, inplace=True)
        print(f"1: {economy_slots}")
        economy_slots['grp_time'] = economy_slots.end_time.diff().dt.seconds.gt(1800).cumsum()
        economy_slots = economy_slots.groupby('grp_time').agg({'start_time': 'min', 'end_time': 'max', 'value_inc_vat': 'mean'})
        print(f"2: {economy_slots}")
        economy_slots.reset_index(drop=True, inplace=True)
        economy_slots['grp_time'] = economy_slots.end_time.diff().dt.seconds.gt(3600).cumsum()
        economy_slots = economy_slots.groupby('grp_time').agg({'start_time': 'min', 'end_time': 'max', 'value_inc_vat': 'mean'})
        #TODO: Re-run the slot merge stuff to merge hours now.  30min adjoining slots are now 1 hour slots, but the 1 hr slots might adjoin too.
        economy_slots.reset_index(drop=True, inplace=True)
        self.economy_slots = economy_slots
        print(f"3: {economy_slots}")
        return economy_slots
    def write_to_influxdb(self):
        # You need the index to be a time column otherwise InfluxDB will not accept it. (e.g. index "0" = epoch zero = 1970-01-01 00:00:00 = a long time ago = outside the RP of the bucket)
        influx_df = self.prices.set_index('start_time')
        with InfluxDBClient(url=api_key.influxdb_url, token=api_key.influxdb_token, org=api_key.influxdb_org) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=api_key.influxdb_bucket, record=influx_df, data_frame_measurement_name='agile_prices')
        print("Prices written to InfluxDB")


    
def program_charging_schedule(slot_list):
    sync_inverter_time()
    zero_charging_slots()
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    a,b = [],[]
    for slot in slot_list[0:3]:
        a.extend(slot)
    for slot in slot_list[3:6]:
        b.extend(slot)
    print(a)
    print(b)
    client.write_registers(1100, a, slave=1)
    client.write_registers(1018, b, slave=1)
    client.close()

def set_economy_charging(prices):
    print("Setting economy charging")
    economy_slots = prices.get_economy_slots()
    print(economy_slots)
    #return True
    charging_slots_list = []
    for r in economy_slots.itertuples():
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
    program_charging_schedule(charging_slots_list)



def parse_args():
    parser = ArgumentParser(description="Control Growatt SPH inverters and batteries to charge the battery at the cheapest time possible using Agile Octopus.")
    programming_group = parser.add_argument_group("Charge Programming")
    programming_group.add_argument("-z", "--zero", dest="zero", help="Zero out the battery charging schedule", action="store_true")
    programming_group.add_argument("-d", "--duration", dest="duration", help="Set the duration of the charge in minutes.  Default is 240 (4 hours)", default=240, type=int)
    programming_group.add_argument("-st", "--start-time", dest="start_time", help="Set the earliest time to search for a slot for the charge.", type=datetime.datetime.fromisoformat)
    programming_group.add_argument("-et", "--end-time", dest="end_time", help="Set the latest time to search for a slot for the charge.  Default is now + 4 hours. YYYY-MM-DDTHH:MM:SS", type=datetime.datetime.fromisoformat)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("-e", "--economy", dest="economy", help="Program the cheapest over-night charging schedule possible", action="store_true")
    mode_group.add_argument("-4", "--4hour", dest="4hour", help="Program the cheapest 4 hour charging schedule possible", action="store_true")
    mode_group.add_argument("-2", "--2hour", dest="2hour", help="Program the cheapest 2 hour charging schedule possible", action="store_true")

    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument("-c", "--cheap", dest="cheap", help="Set the threshold for cheap electricity in p/kWh.  Default is 15", type=float)
    config_group.add_argument("-i", "--inverter", dest="inverter", help="Set the inverter address.  Default is ew11-1", default='ew11-1')
    #config_group.add_argument("-b", "--battery", dest="battery", help="Set the battery size in kWh.  Default is 16kWh", default=16, type=int)
    config_group.add_argument("-r", "--rate", dest="rate", help="Set the maximum AC charge rate in kW.  Default is 100%%", default=100, type=int)
    config_group.add_argument("-D", "--debug", dest="debug", help="Enable debug output", action="store_true")

    info_group = parser.add_argument_group("Information")
    info_group.add_argument("-v", "--version", dest="version", help="Print version information", action="store_true")
    info_group.add_argument("-C", "--soc", dest="soc", help="Return state of charge of the battery in %%", action="store_true")
    info_group.add_argument("-S", "--schedule", dest="schedule", help="Return the current charging schedule", action="store_true")
    info_group.add_argument("-P", "--prices", dest="prices", help="Return the current Agile prices", action="store_true")
    info_group.add_argument("-I", "--influx", dest="influx", help="Write the current prices to InfluxDB", action="store_true")
    # TODO: Add a dummy run option to just print the schedule and not program the inverter
    # TODO: Add a "stop charging at soc%" option
    #     

    args = parser.parse_args()
    print(args)
    return args


def start_of_next_period():
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

def get_battery_soc():
    # Battery state of charge s held in register 1014
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    results = client.read_input_registers(1014, 1, slave=1)
    client.close()
    return results.registers[0]

def sync_inverter_time():
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    system_now = datetime.datetime.now()
    result = client.write_registers(45, [system_now.year-2000, system_now.month, system_now.day, system_now.hour, system_now.minute, system_now.second], slave=1)
    client.close()

def get_current_charging_slots():
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    charging_slots = []
    charging_slots.extend(client.read_holding_registers(1100, 9, slave=1).registers)
    charging_slots.extend(client.read_holding_registers(1018, 9, slave=1).registers) # Looks like the docs are wrong here. 1018 is the start of the charging slots not 1017 
    charge_limit = client.read_holding_registers(1091, 1, slave=1).registers[0]
    ac_charge_enabled = client.read_holding_registers(1092, 1, slave=1).registers[0]
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

def zero_charging_slots():
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    result = client.write_registers(1100, [0]*9, slave=1)
    result = client.write_registers(1018, [0]*9, slave=1)
    client.close()

def get_solar_production_tomorrow():
    url = "https://api.forecast.solar/estimate/watthours/day/52.1322466021396/-0.21998598515728754/27/-80/6.720"
    # Might change this to use the per-hour data.  Then we can see how much solar is left for the day.
    # That might mean signing up for an account, then we can hit the API once a minute if we really want to
    headers = {"Accept": "application/json"}
    r = requests.get(url, headers=headers)
    return r.json()['result'][(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')]


# If we want to look up the users region etc we probably need to use the authenticated API
# For now though, I don't need to.
# account_number = api_key.account_number
# api_key = api_key.api_key

def main():
    global prices
    global start_time
    global end_time
    args = parse_args()
    if args.inverter:
        inverter_addr = args.inverter
    if args.zero:
        zero_charging_slots()
    if args.cheap:
        global cheap
        cheap = args.cheap
    if args.schedule:
        get_current_charging_slots()
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
    if args.economy:
        if prices is None:
            prices = Prices()
        set_economy_charging(prices)
    if args.influx:
        if prices is None:
            prices = Prices()
        prices.write_to_influxdb()
    if args.prices:
        if prices is None:
            prices = Prices()
        print(prices.prices.to_markdown())
        print(prices.get_two_hour_windows().to_markdown())
        print(prices.get_four_hour_windows().to_markdown())

    


    sys.exit()


if __name__ == "__main__":
    main()



base_url = "https://api.octopus.energy/v1/"
product_code = "AGILE-FLEX-22-11-25"

tariff_code = "E-1R-AGILE-FLEX-22-11-25-A" # https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25
agile_price_url = base_url + "products/" + product_code + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/"
agile_price_url += "?period_from=" + datetime.datetime.now().isoformat() + "Z"

print("URL: " + agile_price_url)
r = requests.get(agile_price_url)
prices_dict = r.json()

start_time    = pd.DatetimeIndex(x['valid_from'] for x in prices_dict['results'])
end_time      = pd.DatetimeIndex(x['valid_to'] for x in prices_dict['results'])
value_inc_vat = [x['value_inc_vat'] for x in prices_dict['results']]
prices = pd.DataFrame({'start_time':start_time, 'end_time': end_time, 'value_inc_vat': value_inc_vat})
prices.sort_values(by="start_time", inplace=True)
min_price = prices[prices.value_inc_vat == prices.value_inc_vat.min()] # Keep it as a frame to keep the start and end times
max_price = prices[prices.value_inc_vat == prices.value_inc_vat.max()]
avg_price = prices.mean(numeric_only=True).values[0]

# Get the rolling windows for longer charging periods and drop the NaNs
two_hour_windows = prices.rolling('2h', min_periods=4, on='start_time').mean()
four_hour_windows = prices.rolling('4h', min_periods=8, on='start_time').mean()
two_hour_windows.dropna(inplace=True)
four_hour_windows.dropna(inplace=True)
# Sort them in place by price
two_hour_windows.sort_values(by='value_inc_vat', inplace=True)
four_hour_windows.sort_values(by='value_inc_vat', inplace=True)
# Drop any rows which have a higher than average price
two_hour_windows.drop(two_hour_windows[two_hour_windows.value_inc_vat > avg_price].index, inplace=True)
four_hour_windows.drop(four_hour_windows[four_hour_windows.value_inc_vat > avg_price].index, inplace=True)
# Remove any overlapping windows
two_hour_windows = remove_overlap(two_hour_windows, pd.Timedelta('1h30m'))
four_hour_windows = remove_overlap(four_hour_windows, pd.Timedelta('3h30m'))
two_hour_windows = add_window_bounds(two_hour_windows, pd.Timedelta('1h30m'))
four_hour_windows = add_window_bounds(four_hour_windows, pd.Timedelta('3h30m'))

# Find the 30 min slots which are cheaper than the average four hour window
# i.e. drop 30 min slots which are more expensive than could be achieved by charging for 4 hours
cheapest_30min_slots = prices.sort_values(by="value_inc_vat").drop(prices[prices.value_inc_vat > four_hour_windows.mean(numeric_only=True).values[0]].index)

print("----------\n\n\n")
print(f"Minimum price: {min_price['value_inc_vat'].values[0]} at {min_price.start_time.values[0]} until {min_price['end_time'].values[0]}")
print(f"Maximum price: {max_price['value_inc_vat'].values[0]} at {max_price.start_time.values[0]} until {max_price['end_time'].values[0]}")
print(f"Average price: {str(avg_price)}")
print(f"Average 2 hour cost: {str(two_hour_windows.mean(numeric_only=True).values[0])}")
print(f"Average 4 hour cost: {str(four_hour_windows.mean(numeric_only=True).values[0])}")

final_slots = pd.DataFrame()
final_slots = pd.concat([two_hour_windows, four_hour_windows, cheapest_30min_slots])
final_slots['duration'] = final_slots.end_time - final_slots.start_time
final_slots.sort_values(inplace=True, by='value_inc_vat')
final_slots.reset_index(inplace=True, drop=True)
print("\nFinal slots:")
print(final_slots)

print("---------")
print("Cheapest times:")
print(f"2 hour slot:\n{two_hour_windows.head(1)}")
print(f"\n4 hour slot:\n{four_hour_windows.head(1)}")
print(f"\n30 min slot:\n{cheapest_30min_slots.head(1)}")
print(f"\nCheapest 2 hour non-consecutive price: {cheapest_30min_slots.head(4).mean(numeric_only=True).values[0]}")

print("\nCheapest 30mins slots making up four hours before 7AM and after 7PM:")
index = pd.DatetimeIndex(cheapest_30min_slots['start_time'])
overnight_charge = cheapest_30min_slots.iloc[index.indexer_between_time('19:00', '07:00')].sort_values(by='start_time')
overnight_charge.sort_values(by='start_time', inplace=True)
overnight_charge.reset_index(inplace=True, drop=True)
print(overnight_charge)
# Run consecutive 30 min slots together
overnight_charge['grp_time'] = overnight_charge.end_time.diff().dt.seconds.gt(1800).cumsum()
overnight_charge = overnight_charge.groupby('grp_time').agg({'value_inc_vat': 'mean', 'start_time':'min', 'end_time': 'max'})
print(overnight_charge)

charging_slots_list = []
for r in overnight_charge.itertuples():
    start_time = r.start_time
    end_time = r.end_time
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

print(charging_slots_list)
a = input("Press Y & enter to program the inverter")
if a == 'Y' or a == 'y':
    sync_inverter_time()
    zero_charging_slots()
    client = ModbusTcpClient(inverter_addr)
    client.connect()
    a,b = [],[]
    for slot in charging_slots_list[0:3]:
        print(slot)
        a.extend(slot)
    for slot in charging_slots_list[3:6]:
        print(slot)
        b.extend(slot)
    print(a)
    print(b)
    result = client.write_registers(1100, a, slave=1)
    print(result)
    result = client.write_registers(1018, b, slave=1)
    print(result)
    client.close()
else:
    print("Not programming the inverter")



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
print(f"Battery state of charge: {get_battery_soc()}%")
#print(f"Solar generation tomorrow: {get_solar_production_tomorrow()}")
get_current_charging_slots()
#zero_charging_slots()
#get_current_charging_slots()
