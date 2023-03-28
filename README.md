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


## Current state

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

