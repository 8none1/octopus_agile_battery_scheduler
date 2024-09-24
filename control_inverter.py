#!/bin/env python3

from pymodbus.client import ModbusTcpClient
import datetime

client = ModbusTcpClient('ew11-2')
client.connect()
results = client.read_holding_registers(45, 7, slave=1)
year, month, day, hour, minute, second, dow = results.registers
print(results.registers)

system_now = datetime.datetime.utcnow()
inverter_now = datetime.datetime(year, month, day, hour, minute, second)
print(system_now)
print(inverter_now)

if system_now > inverter_now:
    print("System time is ahead of inverter time")
    print((system_now - inverter_now).seconds)
    difference = (system_now - inverter_now).seconds
elif system_now < inverter_now:
    print("System time is behind inverter time")
    print((inverter_now - system_now).seconds)
    difference = (inverter_now - system_now).seconds

if difference > 30:
    print("Difference is greater than 30 seconds")
    print("Setting inverter time to system time")
    print(system_now.year, system_now.month, system_now.day, system_now.hour, system_now.minute, system_now.second, system_now.weekday()+1)
    #result = client.write_registers(50, [system_now.second], slave=1) # , system_now.month, system_now.day, system_now.hour, system_now.minute, system_now.second, system_now.weekday()+1], slave=1)
    result = client.write_registers(45, [system_now.year-2000, system_now.month, system_now.day, system_now.hour, system_now.minute, system_now.second], slave=1) #, system_now.weekday()+1], slave=1)
    print(result)

print("^ Time \n\n  Slots v")

# Holding Registers
# Battery Modes
#  - Slot 1
#    1100 - Start (BB High 8: Hours Low 8: Minutes)
#    1101 - End
#    1102 - Slot Enabled
#  - Slot 2
#    1103 - Start
#    1104 - End
#    1105 - Slot Enabled
#  - Slot 3
#    1106 - Start
#    1107 - End
#    1108 - Slot Enabled
#  - Slot 4
#    1017 - Start
#    1018 - End
#    1019 - Slot Enabled
#  - Slot 5
#    1020 - Start
#    1021 - End
#    1022 - Slot Enabled
#  - Slot 6
#    1023 - Start
#    1024 - End
#    1025 - Slot Enabled
#
# Charge Rate
#   1090 - Battery Charge Rate %
#   1091 - Stop Charge SOC %
#   1092 - AC Charge Enabled
#
# 

# Input Registers
#  118 - Priority Mode (0=Load, 1=Battery, 2=Grid)

# Read battery mode slots

print("\n\nBattery Mode Slots")
results = client.read_holding_registers(1100, 9, slave=1).registers
for e in results:
    if e > 254:
        print(e >> 8, e & 255)
    else:
        print(e)
print("\n\nBattery Mode Slots")
results = client.read_holding_registers(1017, 9, slave=1).registers
for e in results:
    if e > 255:
        print(e >> 8, e & 255)
    else:
        print(e)
print("Batt levels")
results = client.read_holding_registers(1091, 1, slave=1).registers
for e in results:
    if e > 255:
        print(e >> 8, e & 255)
    else:
        print(e)

print("\n\Grid First Slots")
results = client.read_holding_registers(1026, 9, slave=1).registers
for e in results:
    if e > 254:
        print(e >> 8, e & 255)
    else:
        print(e)
print("\n\Grid First Slots")
results = client.read_holding_registers(1080, 9, slave=1).registers
for e in results:
    if e > 255:
        print(e >> 8, e & 255)
    else:
        print(e)
print("Batt levels")
results = client.read_holding_registers(1091, 1, slave=1).registers
for e in results:
    if e > 255:
        print(e >> 8, e & 255)
    else:
        print(e)

print("\n\Load First Slots")
results = client.read_holding_registers(1110, 9, slave=1).registers
for e in results:
    if e > 254:
        print(e >> 8, e & 255)
    else:
        print(e)
print("\n\Load First Slots")
results = client.read_holding_registers(1080, 9, slave=1).registers
for e in results:
    if e > 255:
        print(e >> 8, e & 255)
    else:
        print(e)
print("Batt levels")
results = client.read_holding_registers(1091, 1, slave=1).registers
for e in results:
    if e > 255:
        print(e >> 8, e & 255)
    else:
        print(e)



# Battery Info?
print("\n\nBattery Info")
results = client.read_input_registers(1082, 43, slave=1).registers
a = 1082
for e in results:
    print(f"Register: {a} : {e:04x} | {e}")
    a += 1

# Energy used today?
# 1052 = battery discharge today
# 1056 = battery charge today
# 1060 = load consumption today
print("\n\nEnergy used today")
results = client.read_input_registers(1044, 20, slave=1).registers
a = 1044
print(results)
for e in range(0, len(results), 2):
    b = results[e] << 16 | results[e+1]
    print(f"Register: {a} : {b/10}")
    #print(a*1000)
    a += 2

results = client.read_input_registers(1056, 2, slave=1).registers
a = 1056
print(results)
for e in range(0, len(results), 2):
    b = results[e] << 16 | results[e+1]
    print(f"Register: {a} : {b/10}")
    #print(a*1000)
    a += 2




print("\n\nEnergy used today")
results = client.read_input_registers(100, 20, slave=1).registers
a = 100
print(results)
for e in range(0, len(results), 2):
    b = results[e] << 16 | results[e+1]
    print(f"Register: {a} : {b/10}")
    #print(a*1000)
    a += 2

print("\n\nWork time total")
results = client.read_input_registers(57, 2, slave=1).registers
sum = results[0] << 16 | results[1]
print(f"Register: 57 : {sum}")
print(f"Register: 57 : {(sum/2)/60/60} hours")

print("\n\nLoad load total")
results = client.read_input_registers(1062, 2, slave=1).registers
print(results)
sum = results[0] << 16 | results[1]
print(f"Register: 1062 : {sum/10}kWh")

runtime    = client.read_input_registers(57, 2, slave=1).registers
total_load = client.read_input_registers(1062, 2, slave=1).registers
runtime = ((runtime[0] << 16 | runtime[1]) / 2) / 60 / 60 # Reading is in 0.5 second increments.  Convert to hours.
total_load = (total_load[0] << 16 | total_load[1]) / 10 # Reading is in 0.1kWh increments.  Convert to kWh.
print(f"Runtime: {runtime} hours\nTotal load: {total_load} kWh")
average_load = total_load / runtime
print(f"Average load: {average_load} kWh")

print("Status:")
results = client.read_input_registers(0,100, slave=1).registers
for index, item in enumerate(results):
    print(f"{index}: {item}")


client.close()


