import inspect
if not hasattr(inspect, "getargspec"):
    from inspect import getfullargspec
    inspect.getargspec = lambda fn: getfullargspec(fn)
