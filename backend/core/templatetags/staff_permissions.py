from django import template
from core.staff_access import route_allowed
register = template.Library()


class AccessNode(template.Node):
    def __init__(self, route, content):
        self.route = route
        self.content = content

    def render(self, context):
        return self.content.render(context) if route_allowed(context['request'].user, self.route) else ''


@register.tag('access')
def access(parser, token):
    _, route = token.split_contents()
    content = parser.parse(('endaccess',))
    parser.delete_first_token()
    return AccessNode(route.strip("'\""), content)
