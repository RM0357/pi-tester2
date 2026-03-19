import time
import sys

print("--- LTE Download Simulator Started ---", flush=True)
for i in range(1, 11):
    print(f"Downloading: [{'#' * i}{'.' * (10-i)}] {i*10}%", flush=True)
    time.sleep(0.5)
print("--- Download Complete: connection is ok ---", flush=True)
