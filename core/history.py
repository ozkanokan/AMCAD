from core.project import Project


class ProjectHistory:
    """Bounded immutable snapshots; GUI-independent undo/redo."""
    def __init__(self, project, limit=100):
        self.limit = limit
        self.states = [project.to_dict()]
        self.index = 0
        self.saved_state = self.states[0]

    def record(self, project):
        state = project.to_dict()
        if state == self.states[self.index]:
            return False
        self.states = self.states[:self.index + 1] + [state]
        if len(self.states) > self.limit:
            self.states.pop(0)
        self.index = len(self.states) - 1
        return True

    def undo(self):
        if self.index > 0:
            self.index -= 1
        return Project.from_dict(self.states[self.index])

    def redo(self):
        if self.index < len(self.states) - 1:
            self.index += 1
        return Project.from_dict(self.states[self.index])

    def mark_saved(self, project):
        self.saved_state = project.to_dict()

    def is_dirty(self, project):
        return project.to_dict() != self.saved_state
