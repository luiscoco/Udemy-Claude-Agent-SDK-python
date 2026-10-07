"""Python order fixture for the memory and project-instructions lesson."""
import uuid


def create_order(body):
    total = sum(item["price"] * item["qty"] for item in body["items"])
    return {"id": uuid.uuid4().hex, "total": total}
