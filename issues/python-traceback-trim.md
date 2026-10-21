# Python: trim client frames from server error tracebacks

An exception raised by a server error shows the Python client's own frames between the user's call and the error. A TODO in `client/python/krpc/client.py` asks for the traceback to look as if the exception came from the user's call. Trim the client frames, so the traceback ends at the user's code.
