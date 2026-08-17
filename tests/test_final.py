"""Final integration sanity check."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.jarvis_core import JarvisLocal
import core.jarvis_memory as mem
import core.jarvis_general as gen

print("CORE+MEMORY+GENERAL OK")
mem.record_episode("Who won the Nobel?", "test episode")
mem.update_last_episode("Answer test")
print("episodes:", mem.recent_episodes(1))
print("recall:", mem.format_episode_recall("Nobel")[:150].replace("\n", " | "))
print("gen:", gen.is_general_question("what is the capital of Tunisia"))
