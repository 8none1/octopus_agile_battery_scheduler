# octopus_agile_battery_scheduler

The goal is to automate the charging of a Growatt SPH connected battery to ensure that it is ready for use during the peak periods and to make best use of cheaper periods of electricity,

I'm using partly as an exercise to learn Pandas (so please suggest improvements to the Pandas usage), partly to save a few quid and partly to help save the world (generally speaking; cheap electricity is green electricity)

It will use PyModBus to control the inverter.

## Current state

### 2023-03-19

Running the `agile_prices.py` script will print out the cheapest charging periods based on the current Agile prices.  It calculates:

- The cheapest 30 min time periods.  Cheap is defined as "lowest cost AND lower cost than the average unit cost"
- The cheapest 2 hour continuous time periods
- The cheapest 4 hour continuous time periods

## Other thoughts

I wonder if doing multiple 30 minute charges during the day is "worse" for the batteries than doing one continuous charging period of a few hours.  Hence the two and four hour slots.
If you have any facts on this topic, please share (e.g. via a Github issue).
