from app.tools.room_planner import room_planner
from app.tools.style_advisor import style_advisor
from app.tools.trend_spotter import trend_spotter


def get_tools(context_key: str | None = None) -> list:
    """Return the list of tools available to the agent.

    context_key is accepted for future LaunchDarkly targeting (tool allowlists
    per user segment) but is currently unused.
    """
    return [style_advisor, room_planner, trend_spotter]


__all__ = ["style_advisor", "room_planner", "trend_spotter", "get_tools"]
