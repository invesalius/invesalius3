# Singleton and Publisher-Subscriber design patterns example.

from invesalius.pubsub import pub as Publisher


class Singleton(type):
    # This is a Gary Robinson implementation:
    # http://www.garyrobinson.net/2004/03/python_singleto.html

    def __init__(cls, name, bases, dic):
        super(Singleton, cls).__init__(name, bases, dic)
        cls.instance = None

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance


class Pizza(object):
    # Only one project will be initialized per time. Therefore, we use
    # Singleton design pattern for implementing it
    __metaclass__ = Singleton

    def __init__(self):
        self.npieces = 8
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.RemovePiece, "Eat piece of pizza")

    def RemovePiece(self, pubsub_evt):
        person = pubsub_evt
        if self.npieces:
            self.npieces -= 1
            print(f"{person.name} ate pizza!")
        else:
            print(f"{person.name} is hungry!")


class Person:
    def __init__(self, name):
        self.name = name
        self.pizza = Pizza()

    def EatPieceOfPizza(self):
        Publisher.sendMessage("Eat piece of pizza", pubsub_evt=self)


print("Initial state:")
p1 = Person("Paulo ")
p2 = Person("Thiago")
p3 = Person("Andre ")
people = [p1, p2, p3]

print("Everyone eats 2 pieces:")
for i in range(2):
    for person in people:
        person.EatPieceOfPizza()

print("Everyone tries to eat another piece:")
for person in people:
    person.EatPieceOfPizza()
