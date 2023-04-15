# Singleton design pattern example.

# For more information on singleton:
# http://en.wikipedia.org/wiki/Singleton_pattern
# http://www.vincehuston.org/dp/singleton.html

class Singleton(type):
    # This is a Gary Robinson implementation:
    # http://www.garyrobinson.net/2004/03/python_singleto.html
    def __init__(cls, name: str, bases: tuple, dic: dict) -> None:
        super().__init__(name, bases, dic)
        cls.instance = None

    def __call__(cls, *args: tuple, **kw: dict) -> object:
        if cls.instance is None:
            cls.instance = super().__call__(*args, **kw)
        return cls.instance

class Bone(object):
    # Only one project will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__= Singleton
    
    def __init__(self) -> None:
        self.size: int = 100

    def RemovePart(self, part_size: int) -> None:
        self.size -= part_size


class Dog:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.bone: Bone = Bone()

    def EatBonePart(self, part_size: int) -> None:
        self.bone.RemovePart(part_size)


print("Initial state:")
d1: Dog = Dog("Nina")
d2: Dog = Dog("Tang")
print(f"Bone size of {d1.name}: {d1.bone.size}")
print(f"Bone size of {d2.name}: {d2.bone.size}\n")

print("Only Nina eats:")
d1.EatBonePart(5)
print(f"Bone size of {d1.name}: {d1.bone.size}")
print(f"Bone size of {d2.name}: {d2.bone.size}\n")

print("Tang eats after Nina:")
d2.EatBonePart(20)
print(f"Bone size of {d1.name}: {d1.bone.size}")
print(f"Bone size of {d2.name}: {d2.bone.size}")
