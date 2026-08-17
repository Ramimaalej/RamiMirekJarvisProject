import sys
sys.path.insert(0, '.')
import time, traceback
print("0 import mem", flush=True)
import core.jarvis_memory as mem

print("1 record...", flush=True)
try:
    t0 = time.time()
    mem.record_episode("Who won the Nobel?", "test episode")
    print("1a record done", time.time() - t0, flush=True)
except Exception as e:
    traceback.print_exc()

print("2 update...", flush=True)
try:
    t0 = time.time()
    mem.update_last_episode("Answer test")
    print("2a update done", time.time() - t0, flush=True)
except Exception as e:
    traceback.print_exc()

print("3 recall...", flush=True)
try:
    t0 = time.time()
    r = mem.format_episode_recall("Nobel")
    print("3a recall done", time.time() - t0, flush=True)
    print("recall:", r[:200].replace("\n", " | "), flush=True)
except Exception as e:
    traceback.print_exc()
