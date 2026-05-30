"""Reporter skeleton.

Reports real, shadow, lab and matrix validation metrics separately.
"""

class Reporter:
    def generate(self) -> object:
        raise NotImplementedError

