class Term:
    def __init__(self, id):
        self.id = id
        self.name = ""
        self.children = []
        self.parents = []
        self.alt_names = []

    # Getters
    def get_id(self):
        return self.id

    def get_children(self):
        return self.children

    def get_parents(self):
        return self.parents

    def get_name(self):
        return self.name

    # Setters
    def set_name(self, name):
        self.name = name

    def set_parents(self, parents):
        self.parents = parents

    def set_children(self, children):
        self.children = children

    def set_alt_names(self, alt_names):
        self.alt_names = alt_names

    def get_by_id(self, id):
        if self.id == id:
            return self.name
