# Publisher and subscriber design pattern example.

# More information about this design pattern can be found at:
# http://wiki.wxpython.org/ModelViewController
# http://wiki.wxpython.org/PubSub
from invesalius.pubsub import pub as Publisher

# The maintainer of Pubsub module is Oliver Schoenborn.
# Since the end of 2006 Pubsub is now maintained separately on SourceForge at:
# http://pubsub.sourceforge.net/


class Student:
    def __init__(self, name):
        self.name = name
        self.mood = ":|"
        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(self.ReceiveProject, "Set Student Project")
        Publisher.subscribe(self.ReceiveGrade, "Set Student Grade")

    def ReceiveProject(self, pubsub_evt):
        projects_dict = pubsub_evt
        self.project = projects_dict[self.name]
        print(f"{self.name}: I've received the project {self.project}")

    def ReceiveGrade(self, pubsub_evt):
        grades_dict = pubsub_evt
        self.grade = grades_dict[self.name]
        if self.grade > 6:
            self.mood = ":)"
        else:
            self.mood = ":("
        print(f"{self.name}: I've received the grade {self.grade} {self.mood}")


class Teacher:
    def __init__(self, name, course):
        self.name = name
        self.course = course

    def SendMessage(self):
        print(f"{self.name}: Telling students the projects")
        Publisher.sendMessage("Set Student Project", pubsub_evt=self.course.projects_dict)

        print(f"\n{self.name}: Telling students the grades")
        Publisher.sendMessage("Set Student Grade", pubsub_evt=self.course.grades_dict)


class Course:
    def __init__(self, subject):
        self.subject = subject
        self.grades_dict = {}
        self.projects_dict = {}


# Create students:
s1 = Student("Coelho")
s2 = Student("Victor")
s3 = Student("Thomaz")

# Create subject:
cs102 = Course("InVesalius")
cs102.projects_dict = {"Coelho": "wxPython", "Victor": "VTK", "Thomaz": "PIL"}
cs102.grades_dict = {"Coelho": 7, "Victor": 6.5, "Thomaz": 4}

# Create teacher:
andre = Teacher("Andre", cs102)

andre.SendMessage()
