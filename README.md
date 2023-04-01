# octopus_agile_battery_scheduler

The goal is to automate the charging of a Growatt SPH connected battery to ensure that it is ready for use during the peak periods and to make best use of cheaper periods of electricity,

I'm using this partly as an exercise to learn Pandas (so please suggest improvements to the Pandas usage), partly to save a few quid and partly to help save the world (generally speaking; cheap electricity is green electricity)

It will use PyModBus to control the inverter.

## Usage

Some of these features are not functional yet.  There are more to be added still.  Generally I tried to make "informational" options uppercase.
The actually scheduling options are mutually exclusive.

Here's how I use it at the moment:

- Run with `-P` to get the current prices and see a summary of when the cheap times are.
- Decide if I want to program the cheapest four hour slot or the cheapest two hour slot
- Run again with `-2` or `-4`
- Confirm the program worked by running with `-S`
- If I want to upload the prices to Influx run with `-I`

When programming the inverter the existing programmed charge times are cleared and the inverter time is synced to UTC from your computer's clock.


```
usage: agile_prices.py [-h] [-z] [-d DURATION] [-st START_TIME] [-et END_TIME] [-e | -4 | -2 | -a] [-c CHEAP] [-i INVERTER]
                       [-r RATE] [-D] [--dummy] [-t] [-v] [-C [SOC]] [-S] [-P] [-I]

Control Growatt SPH inverters and batteries to charge the battery at the cheapest time possible using Agile Octopus.

options:
  -h, --help            show this help message and exit
  -e, --economy         Program the cheapest over-night charging schedule possible
  -4, --4hour           Program the cheapest 4 hour charging schedule possible
  -2, --2hour           Program the cheapest 2 hour charging schedule possible
  -a, --auto            Program the cheapest charging schedule possible taking in to account solar conditions and current soc

Charge Programming:
  -z, --zero            Zero out the battery charging schedule
  -d DURATION, --duration DURATION
                        Set the duration of the charge in minutes. Default is 240 (4 hours)
  -st START_TIME, --start-time START_TIME
                        Set the earliest time to search for a slot for the charge.
  -et END_TIME, --end-time END_TIME
                        Set the latest time to search for a slot for the charge. Default is now + 4 hours. YYYY-MM-DDTHH:MM:SS

Configuration:
  -c CHEAP, --cheap CHEAP
                        Set the threshold for cheap electricity in p/kWh. Default is 15
  -i INVERTER, --inverter INVERTER
                        Set the inverter address. Default is ew11-1
  -r RATE, --rate RATE  Set the maximum AC charge rate in kW. Default is 100%
  -D, --debug           Enable debug output
  --dummy               Dummy run. Don't actually program the inverter
  -t, --time            Set the time on the inverter

Information:
  -v, --version         Print version information
  -C [SOC], --soc [SOC]
                        Return the state of charge of the battery in % or set the max. SOC
  -S, --schedule        Return the current charging schedule
  -P, --prices          Return the current Agile prices
  -I, --influx          Write the current prices to InfluxDB

```

## Example Output

```
Min price: 17.64p/kWh 	2023-03-29T21:30:00.000000000 to 2023-03-29T22:00:00.000000000
Max price: 35.06p/kWh 	2023-03-29T15:30:00.000000000 to 2023-03-29T16:00:00.000000000
Avg price: 24.94p/kWh


Cheapest 2 hour window: 20.18p/kWh 	2023-03-28T22:30:00.000000000 to 2023-03-29T00:30:00.000000000
Cheapest 4 hour window: 20.57p/kWh 	2023-03-28T23:00:00.000000000 to 2023-03-29T03:00:00.000000000


All prices in LOCAL time:
|    | start_time                | end_time                  |   value_inc_vat |
|---:|:--------------------------|:--------------------------|----------------:|
| 47 | 2023-03-28 22:00:00+00:00 | 2023-03-28 22:30:00+00:00 |         26.1765 |
| 46 | 2023-03-28 22:30:00+00:00 | 2023-03-28 23:00:00+00:00 |         20.748  |
| 45 | 2023-03-28 23:00:00+00:00 | 2023-03-28 23:30:00+00:00 |         20.727  |
| 44 | 2023-03-28 23:30:00+00:00 | 2023-03-29 00:00:00+00:00 |         20.307  |
| 43 | 2023-03-29 00:00:00+00:00 | 2023-03-29 00:30:00+00:00 |         18.9315 |
| 42 | 2023-03-29 00:30:00+00:00 | 2023-03-29 01:00:00+00:00 |         21.0105 |
| 41 | 2023-03-29 01:00:00+00:00 | 2023-03-29 01:30:00+00:00 |         20.727  |
| 40 | 2023-03-29 01:30:00+00:00 | 2023-03-29 02:00:00+00:00 |         20.79   |
| 39 | 2023-03-29 02:00:00+00:00 | 2023-03-29 02:30:00+00:00 |         21.3885 |
| 38 | 2023-03-29 02:30:00+00:00 | 2023-03-29 03:00:00+00:00 |         20.685  |
| 37 | 2023-03-29 03:00:00+00:00 | 2023-03-29 03:30:00+00:00 |         21.168  |
| 36 | 2023-03-29 03:30:00+00:00 | 2023-03-29 04:00:00+00:00 |         20.181  |
| 35 | 2023-03-29 04:00:00+00:00 | 2023-03-29 04:30:00+00:00 |         23.373  |
| 34 | 2023-03-29 04:30:00+00:00 | 2023-03-29 05:00:00+00:00 |         24.759  |
| 33 | 2023-03-29 05:00:00+00:00 | 2023-03-29 05:30:00+00:00 |         24.318  |
| 32 | 2023-03-29 05:30:00+00:00 | 2023-03-29 06:00:00+00:00 |         30.786  |
| 31 | 2023-03-29 06:00:00+00:00 | 2023-03-29 06:30:00+00:00 |         25.2    |
| 30 | 2023-03-29 06:30:00+00:00 | 2023-03-29 07:00:00+00:00 |         33.957  |
| 29 | 2023-03-29 07:00:00+00:00 | 2023-03-29 07:30:00+00:00 |         29.7675 |
| 28 | 2023-03-29 07:30:00+00:00 | 2023-03-29 08:00:00+00:00 |         28.245  |
| 27 | 2023-03-29 08:00:00+00:00 | 2023-03-29 08:30:00+00:00 |         26.7015 |
| 26 | 2023-03-29 08:30:00+00:00 | 2023-03-29 09:00:00+00:00 |         25.053  |
| 25 | 2023-03-29 09:00:00+00:00 | 2023-03-29 09:30:00+00:00 |         22.575  |
| 24 | 2023-03-29 09:30:00+00:00 | 2023-03-29 10:00:00+00:00 |         21.8925 |
| 23 | 2023-03-29 10:00:00+00:00 | 2023-03-29 10:30:00+00:00 |         21.651  |
| 22 | 2023-03-29 10:30:00+00:00 | 2023-03-29 11:00:00+00:00 |         22.05   |
| 21 | 2023-03-29 11:00:00+00:00 | 2023-03-29 11:30:00+00:00 |         25.053  |
| 20 | 2023-03-29 11:30:00+00:00 | 2023-03-29 12:00:00+00:00 |         23.5725 |
| 19 | 2023-03-29 12:00:00+00:00 | 2023-03-29 12:30:00+00:00 |         22.827  |
| 18 | 2023-03-29 12:30:00+00:00 | 2023-03-29 13:00:00+00:00 |         20.349  |
| 17 | 2023-03-29 13:00:00+00:00 | 2023-03-29 13:30:00+00:00 |         22.05   |
| 16 | 2023-03-29 13:30:00+00:00 | 2023-03-29 14:00:00+00:00 |         19.047  |
| 15 | 2023-03-29 14:00:00+00:00 | 2023-03-29 14:30:00+00:00 |         19.6665 |
| 14 | 2023-03-29 14:30:00+00:00 | 2023-03-29 15:00:00+00:00 |         20.1075 |
| 13 | 2023-03-29 15:00:00+00:00 | 2023-03-29 15:30:00+00:00 |         33.7155 |
| 12 | 2023-03-29 15:30:00+00:00 | 2023-03-29 16:00:00+00:00 |         35.0569 |
| 11 | 2023-03-29 16:00:00+00:00 | 2023-03-29 16:30:00+00:00 |         35.0569 |
| 10 | 2023-03-29 16:30:00+00:00 | 2023-03-29 17:00:00+00:00 |         35.0569 |
|  9 | 2023-03-29 17:00:00+00:00 | 2023-03-29 17:30:00+00:00 |         35.0569 |
|  8 | 2023-03-29 17:30:00+00:00 | 2023-03-29 18:00:00+00:00 |         35.0569 |
|  7 | 2023-03-29 18:00:00+00:00 | 2023-03-29 18:30:00+00:00 |         27.342  |
|  6 | 2023-03-29 18:30:00+00:00 | 2023-03-29 19:00:00+00:00 |         27.867  |
|  5 | 2023-03-29 19:00:00+00:00 | 2023-03-29 19:30:00+00:00 |         27.867  |
|  4 | 2023-03-29 19:30:00+00:00 | 2023-03-29 20:00:00+00:00 |         25.137  |
|  3 | 2023-03-29 20:00:00+00:00 | 2023-03-29 20:30:00+00:00 |         30.6915 |
|  2 | 2023-03-29 20:30:00+00:00 | 2023-03-29 21:00:00+00:00 |         23.814  |
|  1 | 2023-03-29 21:00:00+00:00 | 2023-03-29 21:30:00+00:00 |         22.05   |
|  0 | 2023-03-29 21:30:00+00:00 | 2023-03-29 22:00:00+00:00 |         17.64   |

Cheapest combined TWO HOUR slots in LOCAL time:
|    | start_time                | end_time                  |   value_inc_vat |
|---:|:--------------------------|:--------------------------|----------------:|
|  0 | 2023-03-28 23:30:00+01:00 | 2023-03-29 01:30:00+01:00 |         20.1784 |
|  1 | 2023-03-29 14:00:00+01:00 | 2023-03-29 16:00:00+01:00 |         20.2178 |
|  2 | 2023-03-29 03:00:00+01:00 | 2023-03-29 05:00:00+01:00 |         20.8556 |
|  3 | 2023-03-29 10:00:00+01:00 | 2023-03-29 12:00:00+01:00 |         22.0421 |
|  4 | 2023-03-29 21:00:00+01:00 | 2023-03-29 23:00:00+01:00 |         23.5489 |

Cheapest combined FOUR HOUR slots in LOCAL time:
|    | start_time                | end_time                  |   value_inc_vat |
|---:|:--------------------------|:--------------------------|----------------:|
|  0 | 2023-03-29 00:00:00+01:00 | 2023-03-29 04:00:00+01:00 |         20.5708 |
|  1 | 2023-03-29 12:00:00+01:00 | 2023-03-29 16:00:00+01:00 |         21.5841 |

Cheapest ECONOMY slots in LOCAL time:
|    | start_time                | end_time                  |   value_inc_vat |
|---:|:--------------------------|:--------------------------|----------------:|
|  0 | 2023-03-28 23:30:00+01:00 | 2023-03-29 05:00:00+01:00 |          20.443 |
|  1 | 2023-03-29 22:30:00+01:00 | 2023-03-29 23:00:00+01:00 |          17.64  |
```

## Current state

### 2023-04-01

Added: pull battery count from the inverter.  We assume that each battery is a 6.5kWh battery.  You can override this by passing a `-b <value>` argument.

`auto` mode is now nearly ready for use.  It will try to charge the battery to the correct level for the next day.  If there is enough solar to charge the battery to full tomorrow and service the normal house requirements then the battery will not be charged.  If it runs out over night then you're going to be importing from the grid until the sun comes up.  It will try to schedule a charge if it thinks that the battery won't last the night, but will try to only charge the battery enough to get you to the next morning.  This currently involves a lot of hard-coded guesses and probably won't work very well.  It needs some work still.

If there isn't enough solar tomorrow to fully charge the battery it will try to boost the battery to the required level during the night, i.e. minimise the imported power and use as much solar as possible. It will also try to take in to account how much battery will be lost between the end of the charge and the solar kicking in and stay on grid power a bit longer.

The way it does this is by setting a maximum state of charge (SOC) of the battery but keeping in "Battery First" mode longer.  Battery First mode means that the house will pull from the grid regardless of if the battery is at the required SOC or not and therefore not use any battery power.

If the electricity price is higher than 110% of the minimum 30 minute price then it won't do this, it will stop charging and switch back to load first mode draining the battery to power the house rather than buying the more expensive power.  This can be tweaked in the code, it's not a cli argument yet.

### 2023-03-23

Added the ability to export prices to InfluxDB.  Fixed a few bugs in the economy scheduler.  Started to really get to grips with what this thing needs to do.
Lots more work to do.

### 2023-03-22

Started to add proper cli options to build a proper tool rather than a script that does one job.  It's untidy but I will fix that later.

### 2023-03-21

As well as the longer slots below, the script now calculates the cheapest 30 min slots between 7PM and 7AM and can automatically program the inverter to enable charging for those slots.  This is the first real step towards fully automatic charging.

### 2023-03-19

Running the `agile_prices.py` script will print out the cheapest charging periods based on the current Agile prices.  It calculates:

- The cheapest 30 min time periods.  Cheap is defined as "lowest cost AND lower cost than the average unit cost"
- The cheapest 2 hour continuous time periods
- The cheapest 4 hour continuous time periods

## Other thoughts

I wonder if doing multiple 30 minute charges during the day is "worse" for the batteries than doing one continuous charging period of a few hours.  Hence the two and four hour slots.
If you have any facts on this topic, please share (e.g. via a Github issue).
My solar expert tells me that it'll probably be fine.
Update: It turns out that the cheapest slots during the night often run consecutively, so in practice choosing the cheapest 30 min slots usually works out to be a contiguous 3 hour block.
