def show_environ(environ, start_response):
	start_response('200 OK',[('Content-type','text/html')])
	sorted_keys = environ.keys()
	sorted_keys.sort()
	return [

            '<html><body><h1>Keys in <tt>environ</tt></h1><p>',

            '<br />'.join(sorted_keys),

            '</p></body></html>',

        ]

from wsgiref import simple_server
httpd = simple_server.WSGIServer(
        ('',8080),
        simple_server.WSGIRequestHandler,
    )
httpd.set_app(show_environ)
httpd.serve_forever()
