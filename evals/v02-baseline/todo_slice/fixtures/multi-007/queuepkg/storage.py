class ListStorage:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)

    def pop_front(self):
        # BUG: pops from end (stack) instead of front (queue)
        return self.items.pop()

    def peek_front(self):
        # BUG: peeks last
        return self.items[-1]
