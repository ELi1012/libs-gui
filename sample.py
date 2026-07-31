'''Methods/classes to store the spanning corners 
of a sample.

'''

from dataclasses import dataclass
import math

@dataclass
class Point:
    x: float
    y: float

@dataclass
class SpanEndpoints:
    top_right_corner: Point | None = None
    bottom_left_corner: Point | None = None

    @property
    def width(self) -> float:
        self.validate_points()
        return self.top_right_corner.x - self.bottom_left_corner.x

    @property
    def height(self) -> float:
        self.validate_points()
        return self.top_right_corner.y - self.bottom_left_corner.y

    def validate_points(self):
        if self.top_right_corner is None or self.bottom_left_corner is None:
            raise ValueError("One or both points are None.")
        if self.top_right_corner.x <= self.bottom_left_corner.x:
            raise ValueError("Top right corner must be to the right of the bottom left corner.")
        if self.top_right_corner.y <= self.bottom_left_corner.y:
            raise ValueError("Top right corner must be lower than bottom left corner.")


# Usage
span = SpanEndpoints(Point(40, 50), Point(10, 10))
print(span.height)  # Calculates distance directly from the object
print(span.width)  # Calculates distance directly from the object