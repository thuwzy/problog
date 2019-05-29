%Expected outcome:
% p(1,2) 0.784
% p(2,1) 0.65
% p(3,1) 0.3
% p1(1) 0.8488
% p1(2) 0.86
% p2(1) 0.79
% p2(2) 0.892
% p 0.9244

0.4::a(1).
0.5::a(2).
0.3::b(1).
0.6::b(2).

0.1::c(1,2).
% 0.3::c(2,1).

p(X, Y) :- a(X).
p(X, Y) :- b(Y).
p(X, Y) :- c(X, Y).

p1(X) :- p(X, _).
p2(X) :- p(_, X).
p :- p(_, _).

query(p).
query(p1(1)).
query(p1(2)).
query(p2(1)).
query(p2(2)).
query(p(1,2)).
query(p(2,1)).
query(p(3,1)).



