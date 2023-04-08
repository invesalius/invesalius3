# Publisher and subscriber design pattern example.

# More information about this design pattern can be found at:
# http://wiki.wxpython.org/ModelViewController
# http://wiki.wxpython.org/PubSub
from invesalius.pubsub import pub as Publisher

# The maintainer of Pubsub module is Oliver Schoenborn.
# Since the end of 2006 Pubsub is now maintained separately on SourceForge at:
# http://pubsub.sourceforge.net/


class Student:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.mood = ":|"
        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self.ReceiveProject, "Set Student Project")
        Publisher.subscribe(self.ReceiveGrade, "Set Student Grade")

    def ReceiveProject(self, pubsub_evt) -> None:
        projects_dict: Dict[str, str] = pubsub_evt.data
        self.project = projects_dict[self.name]
        print("%s: I've received the project %s" % (self.name, self.project))

    def ReceiveGrade(self, pubsub_evt) -> None:
        grades_dict: Dict[str, float] = pubsub_evt.data
        self.grade = grades_dict[self.name]
        if self.grade > 6:
            self.mood = ":)"
        else:
            self.mood = ":("
        print("%s: I've received the grade %d %s" % (self.name, self.grade, self.mood))


class Teacher:
    def __init__(self, name: str, course: "Course") -> None:
        self.name: str = name
        self.course: Course = course

    def SendMessage(self) -> None:
        print("%s: Telling students the projects" % (self.name))
        Publisher.sendMessage("Set Student Project", self.course.projects_dict)

        print("\n%s: Telling students the grades" % (self.name))
        Publisher.sendMessage("Set Student Grade", self.course.grades_dict)


class Course:
    def __init__(self, subject) -> None:
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
