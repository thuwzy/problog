%Expected outcome:
% ERROR AccessError

0.3::a(1).
0.4::a(2).
0.5::a(3).

e(1,2).
e(1,3).
e(2,3).
e(3,1).

active(X) :- a(X).
active(X) :- \+ active(Y), e(X,Y), 

query(active(1)).