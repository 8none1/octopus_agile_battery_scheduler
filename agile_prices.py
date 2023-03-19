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
# import api_key

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
        #window_interval = pd.Interval(i1.start_time - pd.Timedelta('1h30m'), i1.start_time + pd.Timedelta('30m'))
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
        #duration_list.append(end_time - start_time)
        values_list.append(each.value_inc_vat)
    #df = pd.DataFrame({'start_time':start_time_list, 'end_time': end_time_list, 'duration': duration_list, 'value_inc_vat': values_list})
    df = pd.DataFrame({'start_time':start_time_list, 'end_time': end_time_list, 'value_inc_vat': values_list})
    return df

# account_number = api_key.account_number
# api_key = api_key.api_key

base_url = "https://api.octopus.energy/v1/"
product_code = "AGILE-FLEX-22-11-25"
tariff_code = "E-1R-AGILE-FLEX-22-11-25-A" # curl -u "$API_KEY:" https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25
agile_price_url = base_url + "products/" + product_code + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/"
#agile_price_url += "?period_from=" + start_of_next_period().isoformat() + "Z"
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
print(two_hour_windows)
print(four_hour_windows)


# Find the 30 min slots which are cheaper than the average price:
cheapest_30min_slots = prices.sort_values(by="value_inc_vat").drop(prices[prices.value_inc_vat > avg_price].index)
print("Cheapest 30 min slots:")
print(cheapest_30min_slots)

print("----------\n\n\n")
print(f"Minimum price: {min_price['value_inc_vat'].values[0]} at {min_price.start_time.values[0]} until {min_price['end_time'].values[0]}")
print(f"Maximum price: {max_price['value_inc_vat'].values[0]} at {max_price.start_time.values[0]} until {max_price['end_time'].values[0]}")
print(f"Average price: {str(avg_price)}")
print(f"Average 2 hour cost: {str(two_hour_windows.mean(numeric_only=True).values[0])}")
print(f"Average 4 hour cost: {str(four_hour_windows.mean(numeric_only=True).values[0])}")

# I don't think we actually care about consecutive slots.  Leaving this here for later in case we do.
# Perhaps 1hr slots would be useful later.
#consecutive_cheap_slots = thirtymin_cheap_slots.copy().sort_values(by="start_time")
#consecutive_cheap_slots['grp_time'] = consecutive_cheap_slots.end_time.diff().dt.seconds.gt(1800).cumsum()
#consecutive_cheap_slots = consecutive_cheap_slots.groupby('grp_time').agg({'value_inc_vat': 'mean', 'end_time': 'max', 'start_time': 'min'})
#consecutive_cheap_slots.sort_values(by='value_inc_vat', inplace=True)
#print("consecutive_cheap_slots sorted by value")
#print(consecutive_cheap_slots)




final_slots = pd.DataFrame()
final_slots = pd.concat([two_hour_windows, four_hour_windows, cheapest_30min_slots])
final_slots['duration'] = final_slots.end_time - final_slots.start_time
final_slots.sort_values(inplace=True, by='value_inc_vat')
final_slots.reset_index(inplace=True, drop=True)
print("Final slots:")
print(final_slots)

# Now we have:
# - Cheapest 2 hour consecutive slots
# - Cheapest 4 hour consecutive slots
# - Cheapest 30 min slots
#
# We could add the cheapest 2 hour NON consecutive slots
# and the cheapest 4 hour NON consecutive slots

# The "auto" program might like to:
# - If using the non consecutive slots to charge, then find if there are actually consecutive slots so that we can collapse them in to one single charging period and therefore save a charging slot on the inverter
# - Remove anything later than the time at which this will run (likely 6pm ish) because those will be recalcualted tomoorrow
# - Remove anything earlier than the 4 or 2 hour bulk slot. If we're going to do a full charge we should try and shift the bulk of the cost to the cheapest slot
# - 

# Get solar prediction for the next 24 hours:  https://api.forecast.solar/estimate/watthours/day/52.1322466021396/-0.21998598515728754/27/-80/6.720
# Can deliver JSON if the "accept" type is set. 


# Strategy:
#  Always charge the battery when the cost is lower than the average cost
#  Aim for contiguous periods of charging where possible
#  Don't miss out on super cheap periods of charging.  The most the battery can charge during 30mins is 4kW * 30 mins = 2kWh which is about 12.5% of the battery capacity
# Wrong. The battery can only charge from AC at a max rate of 2.7kWh it seems.
#  Call it 10% to be safe

# We should read the battery state at the start of the periods and then decide whether to charge or not

