"""A simple greeting Tool."""


def register(server):
    @server.tool()
    def hello_world() -> str:
        """Respond with hello world."""
        return "hello world"
