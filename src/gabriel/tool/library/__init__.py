"""Gabriel Tool Library.

Importing this package registers all built-in tool callables with the
:data:`~gabriel.tool.registry.function_registry` singleton.

Sub-packages
------------
math          : calculate, convert_units, roll_dice
text          : count_words, encode_base64, decode_base64, hash_text
time_tools    : get_time, days_between, get_current_weather
random_tools  : generate_uuid, random_choice, random_number
utility       : ask_question, list_tools
files         : find_file, search_documents, semantic_search
email         : send_email, list_emails, get_email, draft_email,
                reply_email, forward_email, archive_email, mark_email,
                delete_email, label_email, move_email, search_emails,
                get_thread
calendar      : create_event, list_events, get_event, update_event,
                delete_event, find_free_slot, list_calendars,
                accept_invitation, decline_invitation

Usage
-----
Typically you should import only the sub-packages you need so unused
integration deps are never initialised::

    import gabriel.tool.library.math     # registers math.* only
    import gabriel.tool.library.text     # registers text.* only

Or import everything at once::

    import gabriel.tool.library          # registers all built-in tools
"""

# Safe / stateless tools — no external deps beyond stdlib
import gabriel.tool.library.math  # noqa: F401
import gabriel.tool.library.text  # noqa: F401
import gabriel.tool.library.time  # noqa: F401
import gabriel.tool.library.random  # noqa: F401
import gabriel.tool.library.utility  # noqa: F401
import gabriel.tool.library.files  # noqa: F401

# Integration tools — lazy imports to avoid hard-dep failures when
# google-api-python-client / imaplib etc. are not installed.
# Call these explicitly when integration features are needed.
# import gabriel.tool.library.email    # noqa: F401
# import gabriel.tool.library.calendar # noqa: F401
