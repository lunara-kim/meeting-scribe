def get_publisher(config: dict):
    provider = config["publisher"]["provider"]

    if provider == "confluence":
        from .confluence import ConfluencePublisher
        return ConfluencePublisher(config["publisher"]["confluence"])
    if provider == "notion":
        from .notion import NotionPublisher
        return NotionPublisher(config["publisher"]["notion"])

    raise ValueError(f"알 수 없는 publisher provider: {provider}")
