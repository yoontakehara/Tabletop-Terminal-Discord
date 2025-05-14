def format_message(content):
    return f"`{content}*"

def handle_error(error):
    return f"An error occurred: {error}"

def is_valid_channel(channel):
    return channel is not None and channel.permissions_for(channel.guild.me).send_messages

def mention_channel(channel_id):
    """Return a mention string for a channel ID."""
    return f"<#{channel_id}>" if channel_id else "Not set"

def mention_role(role_id):
    """Return a mention string for a role ID."""
    return f"<@&{role_id}>" if role_id else "Not set"

def get_config_value(value, default="Not set"):
    """Return the value if it exists, otherwise a default string."""
    return value if value else default

def safe_fetchone(cursor):
    """Fetch one row from a cursor, return None if nothing found."""
    result = cursor.fetchone()
    return result[0] if result else None

def truncate(text, max_length=100):
    """Truncate text to a maximum length, adding ellipsis if needed."""
    return (text[:max_length - 3] + "...") if text and len(text) > max_length else text

def is_admin(member):
    """Check if a member has administrator permissions."""
    return member.guild_permissions.administrator