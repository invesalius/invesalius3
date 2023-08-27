# Python closure example

def OuterCount(start):
     counter = [start] # counter is 1-element array
     print "passei por fora"
     def InnerCount():
         counter[0] = counter[0] + 1
         print "passei por dentro"
         return counter[0]
     return InnerCount

print "Init counter at 5"
count = OuterCount(5)
print "\nRun counter 3 times"
print count()
print count()
print count()

print "**********"
count = OuterCount(0)
print count()