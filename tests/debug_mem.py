import sys, time
sys.path.insert(0, '.')
import core.jarvis_memory as mem

print("1 import ok", flush=True)
t0 = time.time()
mem.record_episode("Who won the Nobel?", "test episode")
print("2 record OK", time.time() - t0, flush=True)
mem.update_last_episode("Answer test")
print("3 update OK", time.time() - t0, flush=True)
t1 = time.time()
r = mem.format_episode_recall("Nobel")
print("4 recall OK", time.time() - t1, flush=True)
print("recall:", r[:200].replace("\n", " | "))
