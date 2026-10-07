"""Python storefront rendering fixture."""


def render_cart(cart):
    return "\n".join(f"{item['name']} x{item['qty']}" for item in cart["items"])
