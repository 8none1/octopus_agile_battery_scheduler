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



import requests
import pandas as pd
import datetime
try:
    from pymodbus.client import ModbusTcpClient
except:
    print("If you want to control your inverter with this script you need to install pymodbus")
    MODBUS = False

# import api_key

battery_size = 16 # kWh
max_ac_charge_rate = 2.7 # kW
inverter_ip = 'ew11-1'
cheap = 15 # p/kWh anything below this is cheap.
# Get gas price from Octopus API.  If electricity is cheaper than gas then use electricity to heat water.


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
    duration_list   = []
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
    client = ModbusTcpClient(inverter_ip)
    client.connect()
    results = client.read_input_registers(1014, 1, slave=1)
    client.close()
    return results.registers[0]

def sync_inverter_time():
    client = ModbusTcpClient(inverter_ip)
    client.connect()
    results = client.read_holding_registers(45, 7, slave=1)
    year, month, day, hour, minute, second, dow = results.registers
    system_now = datetime.datetime.now()
    inverter_now = datetime.datetime(year, month, day, hour, minute, second)

    if system_now > inverter_now:
        difference = (system_now - inverter_now).seconds
    elif system_now < inverter_now:
        difference = (inverter_now - system_now).seconds

    if difference > 30:
        print("Setting inverter time to system time")
        result = client.write_registers(45, [system_now.year-2000, system_now.month, system_now.day, system_now.hour, system_now.minute, system_now.second], slave=1)
    client.close()

def get_current_charging_slots():
    client = ModbusTcpClient(inverter_ip)
    client.connect()
    charging_slots = []
    charging_slots.extend(client.read_holding_registers(1100, 9, slave=1).registers)
    charging_slots.extend(client.read_holding_registers(1018, 9, slave=1).registers) # Looks like the docs are wrong here. 1018 is the start of the charging slots not 1017 
    charge_level = client.read_holding_registers(1091, 1, slave=1).registers[0]
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
    
    # print(f"Slot 1: {slot1_start_h:02d}:{slot1_start_m:02d} - {slot1_end_h:02d}:{slot1_end_m:02d} Enabled: {slot1_enabled}")
    # print(f"Slot 2: {slot2_start_h:02d}:{slot2_start_m:02d} - {slot2_end_h:02d}:{slot2_end_m:02d} Enabled: {slot2_enabled}")
    # print(f"Slot 3: {slot3_start_h:02d}:{slot3_start_m:02d} - {slot3_end_h:02d}:{slot3_end_m:02d} Enabled: {slot3_enabled}")
    # print(f"Slot 4: {slot4_start_h:02d}:{slot4_start_m:02d} - {slot4_end_h:02d}:{slot4_end_m:02d} Enabled: {slot4_enabled}")
    # print(f"Slot 5: {slot5_start_h:02d}:{slot5_start_m:02d} - {slot5_end_h:02d}:{slot5_end_m:02d} Enabled: {slot5_enabled}")
    # print(f"Slot 6: {slot6_start_h:02d}:{slot6_start_m:02d} - {slot6_end_h:02d}:{slot6_end_m:02d} Enabled: {slot6_enabled}")
    print(f"Charge Level: {charge_level}")
    print(f"AC Charge Enabled: {ac_charge_enabled}")



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
overnight_charge = overnight_charge.groupby('grp_time').agg({'value_inc_vat': 'mean', 'start_time':min, 'end_time': 'max'})
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
    client = ModbusTcpClient(inverter_ip)
    client.connect()
    blank = [0,0,0,0,0,0,0,0,0]
    result = client.write_registers(1100, blank, slave=1)
    result = client.write_registers(1100, blank, slave=1)
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










#consecutive_cheap_slots.sort_values(by='value_inc_vat', inplace=True)
#print("consecutive_cheap_slots sorted by value")
#print(consecutive_cheap_slots)



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

