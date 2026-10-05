"""Delivery states and the customer-facing texts for each state.

These are the only things the Android app ever learns about a flight.
No MAVLink and no telemetry goes past the PC.
"""

# Main flow, in order. A delivery only ever moves forward through this list.
FLOW = [
    "READY",
    "DEPARTED",
    "DELIVERING",
    "PACKAGE_DELIVERED",
    "RETURNING_HOME",
    "COMPLETED",
]

# Terminal state set only by the warehouse operator, never by MAVLink.
CANCELLED = "CANCELLED"

ALL_STATES = FLOW + [CANCELLED]
TERMINAL_STATES = {"COMPLETED", CANCELLED}
IN_FLIGHT_STATES = {"DEPARTED", "DELIVERING", "PACKAGE_DELIVERED", "RETURNING_HOME"}

STATE_TEXT = {
    "READY": {
        "headline": "PREPARING YOUR DELIVERY",
        "message": "Your delivery is being prepared.",
        "notification_title": "📦 Order confirmed",
        "notification_body": "Your delivery is being prepared.",
        "summary": "Preparing",
    },
    "DEPARTED": {
        "headline": "DRONE HAS TAKEN OFF",
        "message": "🚁 Your delivery drone has taken off.",
        "notification_title": "🚁 Drone has taken off",
        "notification_body": "Your delivery drone has taken off and started its journey.",
        "summary": "In progress",
    },
    "DELIVERING": {
        "headline": "DRONE IS ON THE WAY",
        "message": "🚁 Your package is on the way.",
        "notification_title": "🚁 Your package is on the way",
        "notification_body": "Your package is being delivered by an autonomous drone.",
        "summary": "In progress",
    },
    "PACKAGE_DELIVERED": {
        "headline": "PACKAGE DELIVERED",
        "message": "📦 Your package has been delivered.",
        "notification_title": "📦 Package delivered",
        "notification_body": "The drone has released your package at the delivery location.",
        "summary": "Delivered",
    },
    "RETURNING_HOME": {
        "headline": "DRONE RETURNING HOME",
        "message": "🏠 Delivery completed. The drone is returning to the warehouse.",
        "notification_title": "🏠 Drone is returning home",
        "notification_body": "Delivery completed. The drone is returning to the warehouse.",
        "summary": "Delivered",
    },
    "COMPLETED": {
        "headline": "DELIVERY COMPLETED",
        "message": "✓ Delivery completed successfully.",
        "notification_title": "🏠 Drone has returned home",
        "notification_body": "✓ Delivery completed successfully.",
        "summary": "Completed",
    },
    CANCELLED: {
        "headline": "DELIVERY CANCELLED",
        "message": "This delivery was cancelled by the warehouse.",
        "notification_title": "Delivery cancelled",
        "notification_body": "This delivery was cancelled by the warehouse.",
        "summary": "Cancelled",
    },
}


def flow_index(state: str) -> int:
    """Position of a state in the main flow (CANCELLED sorts after everything)."""
    if state in FLOW:
        return FLOW.index(state)
    return len(FLOW)
