# preload_api/core.py

from logos_exceptions import Interrupt
import inspect

# This is a global defined by the python_worker_node before my code runs.
# It will contain the interrupt payload (dict) or be None.
__logos_interrupt_request__ = None

def check_for_interrupt():
    """
    Checks if an external interrupt has been requested.

    If an interrupt is pending, this function will raise a `logos.Interrupt`
    exception, which halts the current execution and returns control to the
    framework. This is a 'cooperative' check; code will not be stopped
    unless this function is called.

    Guidance:
        I should call this periodically in any long-running loops I write.
        Most built-in `logos` API functions will call this for me periodically.
        The framework handles the `Interrupt` exception to provide a polite
        message back to me; I should not try to catch it myself.

    Returns:
        None, if no interrupt is pending.

    Raises:
        logos.Interrupt: If an interrupt has been requested.
    """

    if __logos_interrupt_request__ is not None:
        raise Interrupt()
