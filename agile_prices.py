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
import api_key

def start_of_next_period():
    # Todo: deal with clock changes
    return datetime.datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)

account_number = api_key.account_number
api_key = api_key.api_key

base_url = "https://api.octopus.energy/v1/"
product_code = "AGILE-FLEX-22-11-25"
tariff_code = "E-1R-AGILE-FLEX-22-11-25-A" # curl -u "$API_KEY:" https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25
agile_price_url = base_url + "products/" + product_code + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/"
#agile_price_url += "?period_from=" + start_of_next_period().isoformat() + "Z"
agile_price_url += "?period_from=" + datetime.datetime.now().isoformat() + "Z"

print("URL: " + agile_price_url)
r = requests.get(agile_price_url, auth=(api_key, ''))
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
two_hour_windows = prices.rolling('2h', min_periods=4, on='start_time').mean() # 4 30m slots = 2 hours
four_hour_windows = prices.rolling('4h', min_periods=8, on='start_time').mean() # 8 30m slots = 4 hours
two_hour_windows.dropna(inplace=True)
four_hour_windows.dropna(inplace=True)
# Sort them in place by price
two_hour_windows.sort_values(by='value_inc_vat', inplace=True)
four_hour_windows.sort_values(by='value_inc_vat', inplace=True)
# Drop any rows which have a higher than average price
two_hour_windows.drop(two_hour_windows[two_hour_windows.value_inc_vat > avg_price].index, inplace=True)
four_hour_windows.drop(four_hour_windows[four_hour_windows.value_inc_vat > avg_price].index, inplace=True)
print("Two hour windows:")
print(two_hour_windows)
print("Four hour windows:")
print(four_hour_windows)

print("Removing overlapping 2hr windows")
# Iterate through the windows and drop any overlapping windows.  We are sorted by price
# so the earlier window should be cheapest and so kept.
# From the docs: You should never modify something you are iterating over.
temp_frame = two_hour_windows.copy()

for i1 in two_hour_windows.itertuples():
    window_interval = pd.Interval(i1.start_time - pd.Timedelta('1h30m'), i1.start_time + pd.Timedelta('30m'))
    for i2 in two_hour_windows.itertuples():
        if i1.Index == i2.Index:
            continue
        wi2 = pd.Interval(i2.start_time - pd.Timedelta('1h30m'), i2.start_time + pd.Timedelta('30m'))
        if window_interval.overlaps(wi2):
            if i2.value_inc_vat > i1.value_inc_vat:
                temp_frame.drop(i2.Index, inplace=True, errors='ignore')

two_hour_windows = temp_frame.copy()
print("De-overlapped 2 hour windows:")
print(two_hour_windows)


print("Removing overlapping four hour windows")
temp_frame = four_hour_windows.copy()
for i1 in four_hour_windows.itertuples():
    window_interval = pd.Interval(i1.start_time - pd.Timedelta('3h30m'), i1.start_time  + pd.Timedelta('30m'))
    for i2 in four_hour_windows.itertuples():
        if i1.Index == i2.Index:
            continue
        wi2 = pd.Interval(i2.start_time - pd.Timedelta('3h30m'), i2.start_time + pd.Timedelta('30m'))
        if window_interval.overlaps(wi2):
            if i2.value_inc_vat > i1.value_inc_vat:
                temp_frame.drop(i2.Index, inplace=True, errors='ignore')
four_hour_windows = temp_frame.copy()
print("De-overlapped 4 hour windows:")
print(four_hour_windows)



# Resort by time
two_hour_windows.sort_values(by="start_time", inplace=True)
#four_hour_windows.sort_index(inplace=True)

# Get the cheapest 8 hours over the whole period made up of 30 min slots
cheapest_30min_slots = prices.sort_values(by="value_inc_vat").head(8)
cheapest_30min_slots.drop(cheapest_30min_slots[cheapest_30min_slots.value_inc_vat > avg_price].index, inplace=True)
print("Cheapest 30 min slots:")
print(cheapest_30min_slots)




print("\n\n\n")
print(f"Minimum price: {min_price['value_inc_vat'].values[0]} at {min_price.start_time.values[0]} until {min_price['end_time'].values[0]}")
print(f"Maximum price: {max_price['value_inc_vat'].values[0]} at {max_price.start_time.values[0]} until {max_price['end_time'].values[0]}")
print(f"Average price: {str(avg_price)}")

print("\n Cheapest 2 hour windows:")
print(two_hour_windows.values)
print(two_hour_windows.value_inc_vat)
print("\n Cheapest 4 hour windows:")
print(four_hour_windows.values)
print(four_hour_windows.value_inc_vat)

print(f"\n\nCheapest 2 hour combined 30m slots cost per kWh: {str(cheapest_2h_slots.sum(numeric_only=True).values[0]/4)}")
print(f"Cheapest 4 hour combined 30m slots cost per kWh: {str(cheapest_4h_slots.sum(numeric_only=True).values[0]/8)}")

# I don't think we actually care about consecutive slots.  Leaving this here for later in case we do.
# Perhaps 1hr slots would be useful later.
#consecutive_cheap_slots = thirtymin_cheap_slots.copy().sort_values(by="start_time")
#consecutive_cheap_slots['grp_time'] = consecutive_cheap_slots.end_time.diff().dt.seconds.gt(1800).cumsum()
#consecutive_cheap_slots = consecutive_cheap_slots.groupby('grp_time').agg({'value_inc_vat': 'mean', 'end_time': 'max', 'start_time': 'min'})
#consecutive_cheap_slots.sort_values(by='value_inc_vat', inplace=True)
#print("consecutive_cheap_slots sorted by value")
#print(consecutive_cheap_slots)



# 1. Make a decision about which 2 or 4 hour slots to use.
# Take the average 2 hr cost and if the 4hr slot is lower, then use that

avg_2h_cost = two_hour_windows.mean(numeric_only=True).values[0]
print(f"Average 2 hour cost: {str(avg_2h_cost)}")

print("---------------------")
print(two_hour_windows)
rolling_2h = two_hour_windows.rolling(2, min_periods=2, on='start_time').mean()
print(rolling_2h)
print("---------------------")


#.sum(numeric_only=True) #8 # divide by 8 because there are 8 30 minute slots in one 2 hour period plus one two hour period
#rolling_2h = two_hour_windows.rolling(2, min_periods=2, on='start_time')#.agg("mean", numeric_only=True ) #8 # divide by 8 because there are 8 30 minute slots in one 2 hour period plus one two hour period
rolling_2h.dropna(inplace=True)
print(f"Rolled up cost for 2 * 2 hours (4 hours total charging): {str(rolling_2h)}")

# Iterate over the rolling 2 hour and drop those which are more expensive than the continuous 4 hour slot
for i1 in rolling_2h.itertuples():
    window_cost = i1.value_inc_vat
    print(f"Window cost: {window_cost}")
    print(f"Cheapest 4 hour slots: {cheapest_4h_slots.mean(numeric_only=True).values[0]}")
    if window_cost > cheapest_4h_slots.mean(numeric_only=True).values[0]: # the cheapest 4 hour slot and only the cheapest(I think)
        print(f"Dropping rolling 2 hour window: {i1.Index}")
        rolling_2h.drop(i1.Index, inplace=True)
    else:
        print("I think that the two hour slots were cheaper")
        print("Need to do something about that")

print(f"Rolling 2 hour cost: {str(rolling_2h)}")

final_slots = pd.DataFrame()

for each in four_hour_windows.itertuples():
    window_cost = each.value_inc_vat
    window_end_time =   each.start_time + pd.Timedelta('30m')
    window_start_time = each.start_time - pd.Timedelta('3h30m')
    data = {'start_time': [window_start_time], 'end_time': [window_end_time], 'value_inc_vat': [window_cost]}
    df = pd.DataFrame(data)
    final_slots = pd.concat([final_slots, df])

for each in rolling_2h.itertuples():
    window_cost = each.value_inc_vat/4
    window_end_time =   each.start_time + pd.Timedelta('30m')
    window_start_time = each.start_time - pd.Timedelta('1h30m')
    data = {'start_time': [window_start_time], 'end_time': [window_end_time], 'value_inc_vat': [window_cost]}
    df = pd.DataFrame(data)# , index=[window_start_time])
    final_slots = pd.concat([final_slots, df])

print("Final slots:")
print(final_slots)
print("------------------")

# 2. Remove the overlapping slots from the list of cheap 30 mins slots

temp_frame = thirtymin_cheap_slots.copy()

for each in final_slots.itertuples():
    # 0 is the index (aka the start time, but we have start time anyway now)
    value_inc_vat = each.value_inc_vat
    window_interval = pd.Interval(each.start_time, each.end_time)
    for slot in thirtymin_cheap_slots.itertuples():
        #slot_value_inc_vat = slot[1]['value_inc_vat']
        slot_interval = pd.Interval(slot.start_time, slot.end_time)
        if window_interval.overlaps(slot_interval):
            #print(f"Window {window_interval} overlaps slot {slot_interval}")
            temp_frame.drop(slot.Index, inplace=True)

# Build the new column from the frame
start_time_list = []
for each in temp_frame.itertuples():
    slot_start_time = each.start_time
    if slot_start_time not in start_time_list:
        start_time_list.append(slot_start_time)

thirtymin_cheap_slots = temp_frame
thirtymin_cheap_slots['start_time'] = start_time_list
thirtymin_cheap_slots.sort_values(inplace=True, by='value_inc_vat')
thirtymin_cheap_slots = thirtymin_cheap_slots.head(8) # 8 slots should be a full charge
#print("Final 30 min cheap slots:")
#print(thirtymin_cheap_slots)

final_slots = pd.concat([final_slots, thirtymin_cheap_slots])
final_slots['duration'] = final_slots.end_time - final_slots.start_time
final_slots.sort_values(inplace=True, by='value_inc_vat')
final_slots.reset_index(inplace=True, drop=True)
print("FINAL Final slots:")
print(final_slots)
# This isn't the best outcome here, because all the additional slots are grouped around the 4 hour slot because that's when things are cheap.  We could ideally do with also finding the
# cheapest slots during the day as well, just in case.

#  TODO:  Add the cheapest 2 hour slots to the list of slots to use

# The "auto" program might like to:
# - Remove anything later than the time at which this will run (likely 6pm ish) because those will be recalcualted tomoorrow
# - Remove anything earlier than the 4 or 2 hour bulk slot. If we're going to do a full charge we should try and shift the bulk of the cost to the cheapest slot
# - 

# Get solar prediction for the next 24 hours:  https://api.forecast.solar/estimate/watthours/day/52.1322466021396/-0.21998598515728754/27/-80/6.720



# Now make sure that we are charging during the cheapest 30 minute period

# Strategy:
#  Always charge the battery when the cost is lower than the average cost
#  Aim for contiguous periods of charging where possible
#  Don't miss out on super cheap periods of charging.  The most the battery can charge during 30mins is 4kW * 30 mins = 2kWh which is about 12.5% of the battery capacity
#  Call it 10% to be safe

# We should read the battery state at the start of the periods and then decide whether to charge or not













# print(f"Cheapest 8 30 minute windows: {str(prices.sort_values(by='value_inc_vat').head(8))}")

# lowest_2_hour_price = prices.rolling('2h', min_periods=4).sum().min()/4 # 4 30 minute periods in 2 hours
# lowest_2_hour_window_index = prices.rolling('2h', min_periods=4).sum().idxmin()
# lowest_4_hour_price = prices.rolling('4h', min_periods=8).sum().min()/8
# lowest_4_hour_window_index = prices.rolling('4h', min_periods=8).sum().idxmin()

# print("The times shown are the start of the last 30 minute period in the window")
# print("i.e. if the time shown is 08:00 then the window ends at 08:30")

# print(f"Cheapest 2 hour window at: {lowest_2_hour_window_index}.  Unit price: {str(lowest_2_hour_price)} ")
# print(f"Cheapest 4 hour window at: {lowest_4_hour_window_index}.  Unit price: {str(lowest_4_hour_price)} ")



# Find the cheapest 2 hour windows which are non overlapping



# If you switch the inverter to Battery First when the sun is shining it will import from the grid to make up the difference in order to charge the battery at 4kW.


#print(f"Lowest 2 hour window: {str(prices.rolling(4).sum().min())} at {prices.rolling(2).sum().idxmin()}")
# print(f"Average price is: {str(prices.rolling(4).)}")

#print(f"Lowest 4 hour window: {str(prices.rolling(8).sum().min())} at {prices.rolling(8).sum().idxmin()}")

#print(f"Lowest 2 2 hour windows: {str(prices.rolling(4).sum().nsmallest(2))}")