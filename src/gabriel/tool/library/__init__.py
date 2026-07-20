"""Gabriel Tool Library.

Tool callables in this package are indexed dynamically by
:class:`gabriel.tool.discovery.ToolLibraryIndexer`, which walks every
sub-package with :mod:`pkgutil` and registers each public async function
matching its module name. Sub-packages are never imported eagerly here —
the indexer imports each one independently, so integration packages with
optional third-party dependencies (``email``, ``calendar``) are only
imported when the indexer actually runs.

Sub-packages
------------
math          : calculate, convert_units, roll_dice
text          : count_words, encode_base64, decode_base64, hash_text
time          : get_time, days_between, get_current_weather
random        : generate_uuid, random_choice, random_number
utility       : ask_question, list_tools
files         : find_file, search_documents, semantic_search
email         : send_email, list_emails, get_email, draft_email,
                reply_email, forward_email, archive_email, mark_email,
                delete_email, label_email, move_email, search_emails,
                get_thread
calendar      : create_event, list_events, get_event, update_event,
                delete_event, find_free_slot, list_calendars,
                accept_invitation, decline_invitation
"""
