from numpy import *
from math import sqrt

class Bases:
    
    def __init__(self, p1, p2, p3):
                
        self.p1 = array([p1[0], p1[1], p1[2]])
        self.p2 = array([p2[0], p2[1], p2[2]])
        self.p3 = array([p3[0], p3[1], p3[2]])
        
        print "p1: ", self.p1
        print "p2: ", self.p2
        print "p3: ", self.p3

        self.sub1 = self.p2 - self.p1
        self.sub2 = self.p3 - self.p1
        
    def Basecreation(self):
        #g1
        g1 = self.sub1
        
        #g2
        lamb1 = g1[0]*self.sub2[0] + g1[1]*self.sub2[1] + g1[2]*self.sub2[2]
        lamb2 = dot(g1, g1)
        lamb = lamb1/lamb2
        
        #Ponto q    
        q = self.p1 + lamb*self.sub1
         
        #g1 e g2 com origem em q   
        g1 = self.p1 - q
        g2 = self.p3 - q
        
        #testa se o g1 nao eh um vetor nulo
        if g1.any() == False:
            g1 = self.p2 - q
            
        #g3 - Produto vetorial NumPy
        g3 = cross(g2, g1)
        
        #normalizacao dos vetores
        g1 = g1/sqrt(lamb2)
        g2 = g2/sqrt(dot(g2, g2))
        g3 = g3/sqrt(dot(g3, g3))
        
        ##tentativa de corrigir o erro na fatia axial que esta invertida 
        g2 = -g2
            
        M = matrix([[g1[0],g1[1],g1[2]], [g2[0],g2[1],g2[2]], [g3[0],g3[1],g3[2]]])
        q.shape = (3, 1)
        q = matrix(q.copy())
        print"M: ", M
        print
        print"q: ", q
        print
        Minv = M.I
        
        return M, q, Minv