from sanic.exceptions import ServerError
from sanic.response import HTTPResponse
from sanic.views import HTTPMethodView
from collections import Mapping
import asyncio
import functools
import jinja2


__version__ = '0.1.2'


# Constants
APP_CONTEXT_PROCESSORS_KEY = 'sanic_jinja2_context_processors'
APP_KEY = 'sanic_jinja2_environment'
REQUEST_CONTEXT_KEY = 'sanic_jinja2_context'


class SanicJinjia2Exception(Exception):
    pass


def setup(app, *args, app_key=APP_KEY, context_processors=(),
          filters=None, **kwargs):
    """
    Initialize jinja2.Environment object.

    :param app: a Sanic instance
    :param app_key: an optional key for application instance. If not
                    provided, default value will be used.
    :param context_processors: context processors that will be used in
                               request middlewares.
    :param args and kwargs: will be passed to environment constructor.
    """
    env = jinja2.Environment(*args, **kwargs)

    # filters
    if filters is not None:
        env.filters.update(filters)

    # app_key
    if not hasattr(app, app_key):
        setattr(app, app_key, env)

    # context_processors
    if context_processors:
        if not hasattr(app, APP_CONTEXT_PROCESSORS_KEY):
            setattr(app, APP_CONTEXT_PROCESSORS_KEY, context_processors)

        app.request_middleware.append(context_processors_middleware)

    env.globals['app'] = app

    return env


def get_env(app, *, app_key=APP_KEY):
    """
    Get Jinja2 env by `app_key`.

    :param app: a Sanic instance
    :param app_key: a optional key for application instance. If not provided,
                    default value will be used.
    """
    return getattr(app, app_key, None)


def render_string(template_name, request, context, *, app_key=APP_KEY):
    """
    Render a string by filling Template template_name with context.
    Returns a string.

    :param template_name: template name.
    :param request: a parameter from web-handler, sanic.request.Request instance.
    :param context: context for rendering.
    :param app_key: a optional key for application instance. If not provided,
                    default value will be used.
    """
    env = get_env(request.app, app_key=app_key)
    if not env:
        raise ServerError(
            "Template engine has not been initialized yet.",
            status_code=500,
        )
    try:
        template = env.get_template(template_name)
    except jinja2.TemplateNotFound as e:
        raise ServerError(
            "Template '{}' not found".format(template_name),
            status_code=500,
        )
    if not isinstance(context, Mapping):
        raise ServerError(
            "context should be mapping, not {}".format(type(context)),
            status_code=500,
        )
    try:
        context = dict(request.ctx.__dict__[REQUEST_CONTEXT_KEY], **context)
    except KeyError:
        pass
    text = template.render(context)
    return text


def render_template(template_name, request, context, *,
                    app_key=APP_KEY, encoding='utf-8',
                    headers=None, status=200):
    """
    Return sanic.response.Response which contains template template_name filled with context.
    Returned response has Content-Type header set to 'text/html'.

    :param template_name: template name.
    :param request: a parameter from web-handler, sanic.request.Request instance.
    :param context: context for rendering.
    :param encoding: response encoding, 'utf-8' by default.
    :param status: HTTP status code for returned response, 200 (OK) by default.
    :param app_key: a optional key for application instance. If not provided,
                    default value will be used.
    """
    if context is None:
        context = {}

    text = render_string(template_name, request, context, app_key=app_key)
    content_type = "text/html; charset={encoding}".format(encoding=encoding)

    return HTTPResponse(
        text, status=status, headers=headers,
        content_type=content_type
    )


def template(template_name, *, app_key=APP_KEY, encoding='utf-8',
             headers=None, status=200):
    """
    Decorate web-handler to convert returned dict context into sanic.response.Response
    filled with template_name template.

    :param template_name: template name.
    :param request: a parameter from web-handler, sanic.request.Request instance.
    :param context: context for rendering.
    :param encoding: response encoding, 'utf-8' by default.
    :param status: HTTP status code for returned response, 200 (OK) by default.
    :param app_key: a optional key for application instance. If not provided,
                    default value will be used.
    """
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):

            if asyncio.iscoroutinefunction(func):
                coro = func
            else:
                coro = asyncio.coroutine(func)

            context = await coro(*args, **kwargs)

            if isinstance(context, HTTPResponse):
                return context

            if isinstance(args[0], HTTPMethodView):
                request = args[1]
            else:
                request = args[0]

            return render_template(template_name, request, context,
                                   app_key=app_key, encoding=encoding)
        return wrapped

    return wrapper


async def context_processors_middleware(request):
    request[REQUEST_CONTEXT_KEY] = {}
    for processor in getattr(request.app, APP_CONTEXT_PROCESSORS_KEY):
        request[REQUEST_CONTEXT_KEY].update(
            await processor(request)
        )
    return None


async def request_processor(request):
    return {
        'request': request
    }
