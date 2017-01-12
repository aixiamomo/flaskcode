# -*- coding: utf-8 -*-
"""
    flask
    ~~~~~

    A microframework based on Werkzeug.  It's extensively documented
    and follows best practice patterns.

    :copyright: (c) 2010 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.


    flask: 微型web框架.
    - 核心依赖:
        - Werkzeug :
            - 功能实现: request, response
            - 导入接口: 部分未实现接口, 直接导入用
        - jinja2 :
            - 功能实现:
            - 导入接口: 模板

    - 核心功能模块:
        - Request()    # 未实现,借用自 Werkzeug
        - Response()   # 未实现,借用自 Werkzeug
        - Flask()      # 核心功能类
"""
from __future__ import with_statement  # 使 with 兼容2.5以前的版本
import os
import sys

from threading import local
from jinja2 import Environment, PackageLoader, FileSystemLoader  # flask 部分模块实现，依赖 jinja2


# 说明：
#   - flask 部分模块实现，严重依赖 werkzeug
#   - werkzeug 最新版本，模块组织结构发生变化。
#   - 故替换部分失效导入包语句，请注意
#   - 最后一条导入语句已失效，暂未找到有效替换
#
from werkzeug.wrappers import Request as RequestBase, Response as ResponseBase  # 两个关键依赖
from werkzeug.local import LocalStack, LocalProxy       # 文件末尾，_request_ctx_stack, current_app 中依赖
from werkzeug.wsgi import SharedDataMiddleware          # Flask() 模块 中引用
from werkzeug.utils import cached_property
from werkzeug import create_environ                     # 已失效

from werkzeug.routing import Map, Rule                  # 路由相关类
from werkzeug.exceptions import HTTPException, InternalServerError  # 两大错误
from werkzeug.contrib.securecookie import SecureCookie  # 安全Cookie类

# utilities we import from Werkzeug and Jinja2 that are unused
# in the module but are exported as public interface.
# utilities 我们从Werkzeug 和 Jinja2中导入，在模块中未使用，但是作为公共接口导出 （间接导入，如 from flask import abort, redirect）
from werkzeug import abort, redirect        # werkzeug 依赖: 本文件未使用,但导入以用作 对外接口
from jinja2 import Markup, escape           # jinja2 的依赖: 本文件未使用,但导入以用作 对外接口

# use pkg_resource if that works, otherwise fall back to cwd.  The
# current working directory is generally not reliable with the notable
# exception of google appengine.
try:
    import pkg_resources
    pkg_resources.resource_stream
except (ImportError, AttributeError):
    pkg_resources = None


################################################################################
#                             代码主体部分
# 说明：
#   - 主要模块：
#       - Request()     # 未独立实现，依赖 werkzeug
#       - Response()    # 未独立实现，依赖 werkzeug
#       - Flask()       # web 框架核心模块
#
#   - 对外接口函数：
#       - url_for()
#       - flash()
#       - get_flashed_messages
#       - render_template()
#       - render_template_string()
#
#   - 全局上下文对线：
#       - _request_ctx_stack  # ctx: context 上下文  stack: 栈
#       - current_app
#       - request
#       - session
#       - g
#
#   - 辅助模块：
#       - _RequestGlobals()
#       - _RequestContext()
# todo: 注解说明
#
################################################################################


class Request(RequestBase):         # 未独立实现，依赖 werkzeug.Request
    """The request object used by default in flask.  Remembers the
    matched endpoint and view arguments.

    It is what ends up as :class:`~flask.request`.  If you want to replace
    the request object used you can subclass this and set
    :attr:`~flask.Flask.request_class` to your subclass.

    默认情况下使用的请求对象。
    记得匹配端点 endpoint 和视图参数 view arguments

    It is what ends up as :class:`~flask.request`.
    如果你想替换这个request对象，你可以子类化这个类，
    并且(给Flask类）设置属性：flask.Flask.request_class = your subclass
    """

    def __init__(self, environ):
        RequestBase.__init__(self, environ)  # 调用父类来初始化
        self.endpoint = None
        self.view_args = None


class Response(ResponseBase):       # 未独立实现，依赖 werkzeug.Response
    """The response object that is used by default in flask.  Works like the
    response object from Werkzeug but is set to have a HTML mimetype by
    default.  Quite often you don't have to create this object yourself because
    :meth:`~flask.Flask.make_response` will take care of that for you.

    If you want to replace the response object used you can subclass this and
    set :attr:`~flask.Flask.request_class` to your subclass.

    默认情况下使用的响应对象。
    就像Werkzeug的响应对象，但默认设置了一个HTML文件类型。
    通常你不必自己创建这个对象，因为 :meth:`~flask.Flask.make_response` 会为你照顾它(这个相应对象)
    """
    default_mimetype = 'text/html'


class _RequestGlobals(object):      # 预定义接口：_RequestContext() 中引用
    pass


class _RequestContext(object):      # 请求上下文，在flask.request_context() 中引用
    """The request context contains all request relevant information.  It is
    created at the beginning of the request and pushed to the
    `_request_ctx_stack` and removed at the end of it.  It will create the
    URL adapter and request object for the WSGI environment provided.

    这个请求上下文包含了所有请求相关的信息。
    请求上下文创建在请求开始时，并且推入'_request_ctx_stack'中，最后删除。
    它将创建URL 适配器，并为 WSGI environment 提供 request 对象。
    """

    def __init__(self, app, environ):
        self.app = app
        self.url_adapter = app.url_map.bind_to_environ(environ)
        self.request = app.request_class(environ)

        # 带上下文的 session 实现
        self.session = app.open_session(self.request)

        self.g = _RequestGlobals()
        self.flashes = None

    def __enter__(self):
        _request_ctx_stack.push(self)

    def __exit__(self, exc_type, exc_value, tb):
        # do not pop the request stack if we are in debug mode and an
        # exception happened.  This will allow the debugger to still
        # access the request object in the interactive shell.
        # 如果在调试模式下发生异常，则不要弹出请求堆栈.。
        # 这将允许调试器仍然能够访问交互式shell中的请求对象.。
        if tb is None or not self.app.debug:
            _request_ctx_stack.pop()


def url_for(endpoint, **values):  # 实现依赖：werkzeug.LocalStack模块
    """Generates a URL to the given endpoint with the method provided.

    使用给定的方法生成给定端点的URL

    :param endpoint: the endpoint of the URL (name of the function)， url的端点（函数名）
    :param values: the variable arguments of the URL rule
    """
    return _request_ctx_stack.top.url_adapter.build(endpoint, values)


def flash(message):  # 向页面 输出 一条 flash消息
    """Flashes a message to the next request.  In order to remove the
    flashed message from the session and to display it to the user,
    the template has to call :func:`get_flashed_messages`.

    向下一个请求发送消息。为了从会话中删除闪烁的消息并将其显示给用户，
    模板必须调用：func：`get_flashed_messages`。

    :param message: the message to be flashed.
    """
    session['_flashes'] = (session.get('_flashes', [])) + [message]


def get_flashed_messages():
    """Pulls all flashed messages from the session and returns them.
    Further calls in the same request to the function will return
    the same messages.

    从session中拉取所有flashed消息，并返回它们
    进一步调用相同的请求函数将返回相同的消息。

    """
    flashes = _request_ctx_stack.top.flashes
    if flashes is None:
        _request_ctx_stack.top.flashes = flashes = \
            session.pop('_flashes', [])
    return flashes


def render_template(template_name, **context):  # 渲染模板页面: 通过查找 templates 目录
    """Renders a template from the template folder with the given
    context.

    使用给定的上下文从模板文件夹渲染模板。

    :param template_name: the name of the template to be rendered 将被渲染的模板名称
    :param context: the variables that should be available in the
                    context of the template. 模板上下文中可用的变量.。
    """

    # current_app : 文件结尾定义的 全局上下文对象
    # 实现依赖 werkzeug
    current_app.update_template_context(context)
    return current_app.jinja_env.get_template(template_name).render(context)


def render_template_string(source, **context):  # 渲染模板页面: 通过传入的模板字符串
    """Renders a template from the given template source string
    with the given context.

    使用给定的上下文从模板源字符串渲染模板

    :param template_name: the sourcecode of the template to be
                          rendered
    :param context: the variables that should be available in the
                    context of the template.
    """
    current_app.update_template_context(context)
    return current_app.jinja_env.from_string(source).render(context)


def _default_template_ctx_processor():  # 默认的模板上下文处理器
    """Default template context processor.  Injects `request`,
    `session` and `g`.

    默认的模板上下文处理器。注入了'request', 'session', 'g'
    """
    reqctx = _request_ctx_stack.top  # 文件末尾定义的 全局上下文对象
    return dict(
        request=reqctx.request,
        session=reqctx.session,
        g=reqctx.g
    )


def _get_package_path(name):  # 获取模块包的路径，在Flask()中引用
    """Returns the path to a package or cwd if that cannot be found."""
    try:
        return os.path.abspath(os.path.dirname(sys.modules[name].__file__))
    except (KeyError, AttributeError):
        return os.getcwd()


###################################################################
#                       核心功能接口
#
#
#
###################################################################
class Flask(object):
    """The flask object implements a WSGI application and acts as the central
    object.  It is passed the name of the module or package of the
    application.  Once it is created it will act as a central registry for
    the view functions, the URL rules, template configuration and much more.

    flask对象实现了一个 WSGI应用程序 并作为中心对象。
    它传递应用程序的模块或包的名称。
    一旦创建它，它将作为 视图函数，URL路由规则，模板配置等的 中央注册中心

    The name of the package is used to resolve resources from inside the
    package or the folder the module is contained in depending on if the
    package parameter resolves to an actual python package (a folder with
    an `__init__.py` file inside) or a standard module (just a `.py` file).

    包的名称是用来解析资源

    For more information about resource loading, see :func:`open_resource`.

    Usually you create a :class:`Flask` instance in your main module or
    in the `__init__.py` file of your package like this::

        from flask import Flask
        app = Flask(__name__)
    """

    #: the class that is used for request objects.  See :class:`~flask.request`
    #: for more information.
    request_class = Request     # 用于请求对象的类

    #: the class that is used for response objects.  See
    #: :class:`~flask.Response` for more information.
    response_class = Response   # 用于响应对象的类

    #: path for the static files.  If you don't want to use static files
    #: you can set this value to `None` in which case no URL rule is added
    #: and the development server will no longer serve any static files.
    static_path = '/static'     # 静态资源路径

    #: if a secret key is set, cryptographic components can use this to
    #: sign cookies and other things.  Set this to a complex random value
    #: when you want to use the secure cookie for instance.
    # 如果设置了密钥，加密组件可以用这个来签名cookie和其他东西。
    # 如果要使用安全cookie, 请将其设置为复杂的随机值
    secret_key = None           # 密钥

    #: The secure cookie uses this for the name of the session cookie
    # 安全cookie使用这个session cookie的名称
    session_cookie_name = 'session'  # 安全cookie

    #: options that are passed directly to the Jinja2 environment
    # 直接传递到jinja2 环境的选项
    jinja_options = dict(
        autoescape=True,
        extensions=['jinja2.ext.autoescape', 'jinja2.ext.with_']
    )

    def __init__(self, package_name):
        #: the debug flag.  Set this to `True` to enable debugging of
        #: the application.  In debug mode the debugger will kick in
        #: when an unhandled exception ocurrs and the integrated server
        #: will automatically reload the application if changes in the
        #: code are detected.
        #
        # debug标志，设其为'True'来启用应用程序的调试
        # 在调试模式下，当发生未处理的异常时，调试器将启动，并且如果检测到代码更改，
        # 集成服务器自动重新加载应用程序
        self.debug = False  # 调试模式开关

        #: the name of the package or module.  Do not change this once
        #: it was set by the constructor.
        # 包或者模块的名称，一旦这个值被构造函数设置，就不要改变这个
        #
        # 注意:
        #   - 这个参数,不是随便乱给的
        #   - 要跟实际的 项目工程目录名对应,否则无法找到对应的工程
        #   - 大多数时候都是__name__，所以你会看到实例化Flask时：app = Flask(__name__)
        #
        self.package_name = package_name

        #: where is the app root located?
        # app根位置所在
        #
        # 注意:
        #   - 调用前面定义的 全局私有方法
        #   - 依赖前面的传入参数, 通过该参数, 获取 项目工程源码根目录.
        #
        self.root_path = _get_package_path(self.package_name)  # 获取项目根目录

        #: a dictionary of all view functions registered.  The keys will
        #: be function names which are also used to generate URLs and
        #: the values are the function objects themselves.
        #: to register a view function, use the :meth:`route` decorator.
        # 包含所有注册的视图函数的字典。
        # keys 是函数名称，也用于生成URL，而value是函数对象。
        # 要注册一个视图函数，使用：meth：`route`装饰器。
        self.view_functions = {}    # 视图函数字典

        #: a dictionary of all registered error handlers.  The key is
        #: be the error code as integer, the value the function that
        #: should handle that error.
        #: To register a error handler, use the :meth:`errorhandler`
        #: decorator.
        # 包含所有注册的错误处理程序的字典。
        # key 是错误代码，是一个整数，value是错误处理程序
        # 要注册错误处理程序，使用 meth：`errorhandler`装饰器。
        self.error_handlers = {}          # 错误处理程序字典

        #: a list of functions that should be called at the beginning
        #: of the request before request dispatching kicks in.  This
        #: can for example be used to open database connections or
        #: getting hold of the currently logged in user.
        #: To register a function here, use the :meth:`before_request`
        #: decorator.
        # 在请求分发前被调用的函数列表。
        # 例如用来打开数据库连接或者获取当前已登陆的用户。
        # 要在这里注册一个函数，使用：meth：`before_request`装饰器。
        self.before_request_funcs = []   # 预处理

        #: a list of functions that are called at the end of the
        #: request.  The function is passed the current response
        #: object and modify it in place or replace it.
        #: To register a function here use the :meth:`after_request`
        #: decorator.
        # 在请求结束时调用的函数列表。
        # 该函数传递当前响应对象并将其修改或替换它。
        # 要在这里注册一个函数，使用：meth：`after_request`装饰器。
        self.after_request_funcs = []   # 结束清理

        #: a list of functions that are called without arguments
        #: to populate the template context.  Each returns a dictionary
        #: that the template context is updated with.
        #: To register a function here, use the :meth:`context_processor`
        #: decorator.
        # 无参数调用的函数列表，用于填充模板上下文的。 每个返回一个字典更新模板上下文。
        # 要在这里注册一个函数，使用：meth:'context_processor'
        # 下面默认添加了模板上下文处理器（注入模板中的全局对象）：request,session,g
        self.template_context_processors = [_default_template_ctx_processor]

        # todo: 待深入
        self.url_map = Map()            # 关键依赖：werkzeug.routing.Map

        if self.static_path is not None:    # 处理静态资源
            self.url_map.add(Rule(self.static_path + '/<filename>',
                                  build_only=True, endpoint='static'))
            if pkg_resources is not None:
                target = (self.package_name, 'static')
            else:
                target = os.path.join(self.root_path, 'static')
            self.wsgi_app = SharedDataMiddleware(self.wsgi_app, {
                self.static_path: target
            })

        #: the Jinja2 environment.  It is created from the
        #: :attr:`jinja_options` and the loader that is returned
        #: by the :meth:`create_jinja_loader` function.
        self.jinja_env = Environment(loader=self.create_jinja_loader(),
                                     **self.jinja_options)
        self.jinja_env.globals.update(
            url_for=url_for,
            get_flashed_messages=get_flashed_messages
        )

    def create_jinja_loader(self):
        """Creates the Jinja loader.  By default just a package loader for
        the configured package is returned that looks up templates in the
        `templates` folder.  To add other loaders it's possible to
        override this method.
        """
        if pkg_resources is None:
            return FileSystemLoader(os.path.join(self.root_path, 'templates'))
        return PackageLoader(self.package_name)

    def update_template_context(self, context):
        """Update the template context with some commonly used variables.
        This injects request, session and g into the template context.

        :param context: the context as a dictionary that is updated in place
                        to add extra variables.
        """
        reqctx = _request_ctx_stack.top
        for func in self.template_context_processors:
            context.update(func())

    def run(self, host='localhost', port=5000, **options):
        """Runs the application on a local development server.  If the
        :attr:`debug` flag is set the server will automatically reload
        for code changes and show a debugger in case an exception happened.

        :param host: the hostname to listen on.  set this to ``'0.0.0.0'``
                     to have the server available externally as well.
        :param port: the port of the webserver
        :param options: the options to be forwarded to the underlying
                        Werkzeug server.  See :func:`werkzeug.run_simple`
                        for more information.
        """
        from werkzeug import run_simple
        if 'debug' in options:
            self.debug = options.pop('debug')
        options.setdefault('use_reloader', self.debug)
        options.setdefault('use_debugger', self.debug)
        return run_simple(host, port, self, **options)

    def test_client(self):
        """Creates a test client for this application.  For information
        about unit testing head over to :ref:`testing`.
        """
        from werkzeug import Client
        return Client(self, self.response_class, use_cookies=True)

    def open_resource(self, resource):
        """Opens a resource from the application's resource folder.  To see
        how this works, consider the following folder structure::

            /myapplication.py
            /schemal.sql
            /static
                /style.css
            /template
                /layout.html
                /index.html

        If you want to open the `schema.sql` file you would do the
        following::

            with app.open_resource('schema.sql') as f:
                contents = f.read()
                do_something_with(contents)

        :param resource: the name of the resource.  To access resources within
                         subfolders use forward slashes as separator.
        """
        if pkg_resources is None:
            return open(os.path.join(self.root_path, resource), 'rb')
        return pkg_resources.resource_stream(self.package_name, resource)

    def open_session(self, request):
        """Creates or opens a new session.  Default implementation stores all
        session data in a signed cookie.  This requires that the
        :attr:`secret_key` is set.

        :param request: an instance of :attr:`request_class`.

        创建or打开一个新session，
        默认实现将所有session数据存储在一个cookie签署
        要求设置:attr:`secret_key`
        """
        key = self.secret_key  # 使用session的时候要设置一个密钥app.secret_key
        if key is not None:
            return SecureCookie.load_cookie(request, self.session_cookie_name,
                                            secret_key=key)

    def save_session(self, session, response):
        """Saves the session if it needs updates.  For the default
        implementation, check :meth:`open_session`.

        :param session: the session to be saved (a
                        :class:`~werkzeug.contrib.securecookie.SecureCookie`
                        object)
        :param response: an instance of :attr:`response_class`
        """
        if session is not None:
            session.save_cookie(response, self.session_cookie_name)

    def add_url_rule(self, rule, endpoint, **options):
        """Connects a URL rule.  Works exactly like the :meth:`route`
        decorator but does not register the view function for the endpoint.

        Basically this example::

            @app.route('/')
            def index():
                pass

        Is equivalent to the following::

            def index():
                pass
            app.add_url_rule('index', '/')
            app.view_functions['index'] = index

        :param rule: the URL rule as string
        :param endpoint: the endpoint for the registered URL rule.  Flask
                         itself assumes the name of the view function as
                         endpoint
        :param options: the options to be forwarded to the underlying
                        :class:`~werkzeug.routing.Rule` object
        """
        options['endpoint'] = endpoint
        options.setdefault('methods', ('GET',))
        self.url_map.add(Rule(rule, **options))

    def route(self, rule, **options):
        """A decorator that is used to register a view function for a
        given URL rule.  Example::

            @app.route('/')
            def index():
                return 'Hello World'

        Variables parts in the route can be specified with angular
        brackets (``/user/<username>``).  By default a variable part
        in the URL accepts any string without a slash however a different
        converter can be specified as well by using ``<converter:name>``.

        Variable parts are passed to the view function as keyword
        arguments.

        The following converters are possible:

        =========== ===========================================
        `int`       accepts integers
        `float`     like `int` but for floating point values
        `path`      like the default but also accepts slashes
        =========== ===========================================

        Here some examples::

            @app.route('/')
            def index():
                pass

            @app.route('/<username>')
            def show_user(username):
                pass

            @app.route('/post/<int:post_id>')
            def show_post(post_id):
                pass

        An important detail to keep in mind is how Flask deals with trailing
        slashes.  The idea is to keep each URL unique so the following rules
        apply:

        1. If a rule ends with a slash and is requested without a slash
           by the user, the user is automatically redirected to the same
           page with a trailing slash attached.
        2. If a rule does not end with a trailing slash and the user request
           the page with a trailing slash, a 404 not found is raised.

        This is consistent with how web servers deal with static files.  This
        also makes it possible to use relative link targets safely.

        The :meth:`route` decorator accepts a couple of other arguments
        as well:

        :param rule: the URL rule as string
        :param methods: a list of methods this rule should be limited
                        to (``GET``, ``POST`` etc.).  By default a rule
                        just listens for ``GET`` (and implicitly ``HEAD``).
        :param subdomain: specifies the rule for the subdoain in case
                          subdomain matching is in use.
        :param strict_slashes: can be used to disable the strict slashes
                               setting for this rule.  See above.
        :param options: other options to be forwarded to the underlying
                        :class:`~werkzeug.routing.Rule` object.
        """
        def decorator(f):
            self.add_url_rule(rule, f.__name__, **options)
            self.view_functions[f.__name__] = f
            return f
        return decorator

    def errorhandler(self, code):
        """A decorator that is used to register a function give a given
        error code.  Example::

            @app.errorhandler(404)
            def page_not_found():
                return 'This page does not exist', 404

        You can also register a function as error handler without using
        the :meth:`errorhandler` decorator.  The following example is
        equivalent to the one above::

            def page_not_found():
                return 'This page does not exist', 404
            app.error_handlers[404] = page_not_found

        :param code: the code as integer for the handler
        """
        def decorator(f):
            self.error_handlers[code] = f
            return f
        return decorator

    def before_request(self, f):
        """Registers a function to run before each request."""
        self.before_request_funcs.append(f)
        return f

    def after_request(self, f):
        """Register a function to be run after each request."""
        self.after_request_funcs.append(f)
        return f

    def context_processor(self, f):
        """Registers a template context processor function."""
        self.template_context_processors.append(f)
        return f

    def match_request(self):
        """Matches the current request against the URL map and also
        stores the endpoint and view arguments on the request object
        is successful, otherwise the exception is stored.
        """
        rv = _request_ctx_stack.top.url_adapter.match()
        request.endpoint, request.view_args = rv
        return rv

    def dispatch_request(self):
        """Does the request dispatching.  Matches the URL and returns the
        return value of the view or error handler.  This does not have to
        be a response object.  In order to convert the return value to a
        proper response object, call :func:`make_response`.
        """
        try:
            endpoint, values = self.match_request()
            return self.view_functions[endpoint](**values)
        except HTTPException, e:
            handler = self.error_handlers.get(e.code)
            if handler is None:
                return e
            return handler(e)
        except Exception, e:
            handler = self.error_handlers.get(500)
            if self.debug or handler is None:
                raise
            return handler(e)

    def make_response(self, rv):
        """Converts the return value from a view function to a real
        response object that is an instance of :attr:`response_class`.

        The following types are allowd for `rv`:

        ======================= ===========================================
        :attr:`response_class`  the object is returned unchanged
        :class:`str`            a response object is created with the
                                string as body
        :class:`unicode`        a response object is created with the
                                string encoded to utf-8 as body
        :class:`tuple`          the response object is created with the
                                contents of the tuple as arguments
        a WSGI function         the function is called as WSGI application
                                and buffered as response object
        ======================= ===========================================

        :param rv: the return value from the view function
        """
        if isinstance(rv, self.response_class):
            return rv
        if isinstance(rv, basestring):
            return self.response_class(rv)
        if isinstance(rv, tuple):
            return self.response_class(*rv)
        return self.response_class.force_type(rv, request.environ)

    def preprocess_request(self):
        """Called before the actual request dispatching and will
        call every as :meth:`before_request` decorated function.
        If any of these function returns a value it's handled as
        if it was the return value from the view and further
        request handling is stopped.
        """
        for func in self.before_request_funcs:
            rv = func()
            if rv is not None:
                return rv

    def process_response(self, response):
        """Can be overridden in order to modify the response object
        before it's sent to the WSGI server.  By default this will
        call all the :meth:`after_request` decorated functions.

        :param response: a :attr:`response_class` object.
        :return: a new response object or the same, has to be an
                 instance of :attr:`response_class`.
        """
        session = _request_ctx_stack.top.session
        if session is not None:
            self.save_session(session, response)
        for handler in self.after_request_funcs:
            response = handler(response)
        return response

    def wsgi_app(self, environ, start_response):
        """The actual WSGI application.  This is not implemented in
        `__call__` so that middlewares can be applied:

            app.wsgi_app = MyMiddleware(app.wsgi_app)

        :param environ: a WSGI environment
        :param start_response: a callable accepting a status code,
                               a list of headers and an optional
                               exception context to start the response
        """
        with self.request_context(environ):
            rv = self.preprocess_request()
            if rv is None:
                rv = self.dispatch_request()
            response = self.make_response(rv)
            response = self.process_response(response)
            return response(environ, start_response)

    def request_context(self, environ):
        """Creates a request context from the given environment and binds
        it to the current context.  This must be used in combination with
        the `with` statement because the request is only bound to the
        current context for the duration of the `with` block.

        Example usage::

            with app.request_context(environ):
                do_something_with(request)

        :params environ: a WSGI environment
        """
        return _RequestContext(self, environ)

    def test_request_context(self, *args, **kwargs):
        """Creates a WSGI environment from the given values (see
        :func:`werkzeug.create_environ` for more information, this
        function accepts the same arguments).
        """
        return self.request_context(create_environ(*args, **kwargs))

    def __call__(self, environ, start_response):
        """Shortcut for :attr:`wsgi_app`"""
        return self.wsgi_app(environ, start_response)


###################################################################
#                     全局上下文变量定义(context locals)
# 说明：
#   - 此处全局的 g, session, 需要深入理解
#   - 需要深入去看 werkzeug.LocalStack()的实现
#   - 为了支持多线程
#   - flask0.9之前，只有请求上下文，没有程序上下文
#
###################################################################

# context locals
_request_ctx_stack = LocalStack()  # 一个请求栈（数据结构），依赖 werkzeug.LocalStack 模块
current_app = LocalProxy(lambda: _request_ctx_stack.top.app)
request = LocalProxy(lambda: _request_ctx_stack.top.request)
session = LocalProxy(lambda: _request_ctx_stack.top.session)
g = LocalProxy(lambda: _request_ctx_stack.top.g)
