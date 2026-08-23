'''Methods/classes to store the spanning corners 
of a sample.

'''

from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float

@dataclass
class SpanEndpoints:
    corner1: Point | None = None
    corner2: Point | None = None

    @property
    def width(self) -> float:
        self.validate_points()
        return abs(self.corner1.x - self.corner2.x)

    @property
    def height(self) -> float:
        self.validate_points()
        return abs(self.corner1.y - self.corner2.y)

    def validate_points(self):
        '''Corners must span entire rectangle.'''
        if self.corner1 is None or self.corner2 is None:
            raise ValueError("One or both points are None.")

        x_dist = self.corner1.x - self.corner2.x
        y_dist = self.corner1.y - self.corner2.y

        if x_dist == 0:
            raise ValueError("Corners must span a non-zero x distance.")
        if y_dist == 0:
            raise ValueError("Corners must span a non-zero y distance.")


# Usage Example
if __name__ == "__main__":
    span = SpanEndpoints(Point(40, 50), Point(10, 10))
    print(span.height)
    print(span.width)