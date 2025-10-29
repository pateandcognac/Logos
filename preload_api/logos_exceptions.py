# preload_api/logos_exceptions.py

"""
Defines core exceptions for my framework.
These are used for control flow and should generally not be caught by my own code.
"""

class Interrupt(BaseException):
    """
    Raised when a cooperative interrupt is requested by an external system.
    Inherits from BaseException to avoid being caught by generic 'except Exception' blocks.
    """
    pass