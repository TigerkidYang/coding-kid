from stringkit import to_snake, pad_center, slugify


def test_to_snake_camel():
    assert to_snake("HelloWorld") == "hello_world"


def test_to_snake_spaces():
    assert to_snake("Hello World") == "hello_world"


def test_pad_center():
    assert pad_center("hi", 6) == "  hi  "
    assert pad_center("hi", 5, "*") == "*hi**"


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  Foo   Bar  ") == "foo-bar"
