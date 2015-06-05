#! /usr/bin/env python

"""
Query-based sampler for ProbLog 2.1
===================================

  Concept:
      Each term has a value which is stored in the SampledFormula.
      When an probabilistic atom or choice atom is evaluated:
          - if probability is boolean discrete:
                          determine Yes/No, store in formula and return 0 (True) or None (False)
          - if probability is non-boolean discrete:
                          determine value, store value in formula and return key to value
      Adds builtin sample(X,S) that calls X and returns the sampled value in S.


  How to support evidence?
      => evidence on facts or derived from deterministic data: trivial, just fix value
      => evidence on atoms derived from other probabilistic facts:
          -> query evidence first
          -> if evidence is false, restart immediately
  Currently, evidence is supported through post-processing.
"""

from __future__ import print_function

import sys

from .program import PrologFile
from .logic import Term, Constant
from .engine import DefaultEngine
from .engine_builtin import check_mode
from .formula import LogicFormula
from .core import process_result
from .util import start_timer, stop_timer
import random
import math
import signal

try:

    import numpy.random

    def sample_poisson(l):
        return numpy.random.poisson(l)[0]

except ImportError:
    numpy = None

    def sample_poisson(l):
        # http://www.johndcook.com/blog/2010/06/14/generating-poisson-random-values/
        if l >= 30:
            c = 0.767 - 3.36 / l
            beta = math.pi / math.sqrt(3.0 * l)
            alpha = beta * l
            k = math.log(c) - l - math.log(beta)

            while True:
                u = random.random()
                x = (alpha - math.log((1.0 - u) / u)) / beta
                n = math.floor(x + 0.5)
                if n < 0:
                    continue
                v = random.random()
                y = alpha - beta * x
                lhs = y + math.log(v / (1.0 + math.exp(y)) ** 2)
                rhs = k + n * math.log(l) - math.lgamma(n+1)
                if lhs <= rhs:
                    return n
        else:
            l2 = math.exp(-l)
            k = 1
            p = 1
            while p > l2:
                k += 1
                p *= random.random()
            return k - 1


def sample_value(term):
    """
    Sample a value from the distribution described by the term.
   :param term: term describing a distribution
   :type term: Term
   :return: value of the term, probability of the choice
   :rtype: Constant
    """
    # TODO add discrete distribution
    if term.functor == 'normal':
        a, b = map(float, term.args)
        return Constant(random.normalvariate(a, b)), 0.0
    elif term.functor == 'poisson':
        a = map(float, term.args)
        return Constant(sample_poisson(a)), 0.0
    elif term.functor == 'exponential':
        a = map(float, term.args), 0.0
        return Constant(random.expovariate(a)), 0.0
    elif term.functor == 'beta':
        a, b = map(float, term.args)
        return Constant(random.betavariate(a, b)), 0.0
    elif term.functor == 'gamma':
        a, b = map(float, term.args)
        return Constant(random.gammavariate(a, b)), 0.0
    elif term.functor == 'uniform':
        a, b = map(float, term.args)
        return Constant(random.randrange(a, b)), 0.0
    elif term.functor == 'constant':
        return term.args[0], 1.0
    else:
        raise ValueError("Unknown distribution: '%s'" % term.functor)

class SampledFormula(LogicFormula):
    
    def __init__(self):
        LogicFormula.__init__(self)
        self.facts = {}
        self.groups = {}
        self.probability = 1.0  # Try to compute
        self.values = []
        
    def _isSimpleProbability(self, term):
        return type(term) == float or term.isConstant()
        
    def addValue(self, value):
        self.values.append(value)
        return len(self.values)
        
    def getValue(self, key):
        if key == 0:
            return None
        return self.values[key-1]
    
    def addAtom(self, identifier, probability, group=None):
        if probability is None:
            return 0
        
        if group is None:  # Simple fact
            if identifier not in self.facts:
                if self._isSimpleProbability(probability):
                    p = random.random()
                    prob = float(probability)
                    value = p < prob
                    if value:
                        result_node = self.TRUE
                        self.probability *= prob
                    else:
                        result_node = self.FALSE
                        self.probability *= (1-prob)
                else:
                    value, prob = sample_value(probability)
                    self.probability *= prob
                    result_node = self.addValue(value)
                self.facts[identifier] = result_node
                return result_node
            else:
                return self.facts[identifier]
        else:
            group, result, choice = identifier
            origin = (group, result)
            if identifier not in self.facts:
                if self._isSimpleProbability(probability):
                    p = float(probability)
                    if origin in self.groups:
                        r = self.groups[origin]  # remaining probability in the group
                    else:
                        r = 1.0
                    
                    if r is None or r < 1e-8:   # r is too small or another choice was made for this origin
                        value = False
                        q = 0
                    else:
                        q = p/r
                        value = (random.random() <= q)
                    if value:
                        self.probability *= p
                        self.groups[origin] = None   # Other choices in group are not allowed
                    elif r is not None:
                        self.groups[origin] = r-p   # Adjust remaining probability
                    if value:
                        result_node = self.TRUE
                    else:
                        result_node = self.FALSE
                else:
                    value, prob = sample_value(probability)
                    self.probability *= prob
                    result_node = self.addValue(value)
                self.facts[identifier] = result_node
                return result_node
            else:
                return self.facts[identifier]

    def computeProbability(self) :
        for k, p in self.groups.items():
            if p is not None:
                self.probability *= p
        self.groups = {}
                
    def addAnd(self, content, **kwdargs):
        i = 0
        for c in content:
            if c is not None and c != 0:
                i += 1
            if i > 1:
                raise ValueError("Can't combine sampled predicates. Use sample/2 to extract sample.")
        return LogicFormula.addAnd(self, content)
        
    def addOr(self, content, **kwd):
        i = 0
        for c in content:
            if c is not None and c != 0:
                i += 1
            if i > 1:
                raise ValueError("Can't combine sampled predicates. Make sure bodies are mutually exclusive.")
        return LogicFormula.addOr(self, content, **kwd)

    def toString(self, db, with_facts=False, with_probability=False, oneline=False,
                 as_evidence=False, **extra):
        self.computeProbability()

        if as_evidence:
            base = 'evidence(%s).'
        else:
            base = '%s.'

        lines = []
        for k, v in self.queries():
            if v is not None:
                val = self.getValue(v)
                if val is None:
                    lines.append(base % (str(k)))
                else:
                    if not as_evidence:
                        lines.append('%s = %s.' % (str(k), val))
            elif as_evidence:
                lines.append(base % ('\+' + str(k)))
        if with_facts:
            for k, v in self.facts.items():
                if v == 0:
                    lines.append(base % str(translate(db, k)))
                elif v is None:
                    lines.append(base % ('\+' + str(translate(db, k))))

        if oneline:
            sep = ' '
        else:
            sep = '\n'
        lines = list(set(lines))
        if with_probability:
            lines.append('%% Probability: %.8g' % self.probability)
        return sep.join(lines)

    def toTuples(self):
        lines = []
        for k, v in self.queries():
            if v is not None:
                val = self.getValue(v)
                if val is None:
                    lines.append((k.functor,) + k.args + (None,))
                else:
                    lines.append((k.functor,) + k.args + (val,))
        return list(set(lines))
        

def translate(db, atom_id):
    if type(atom_id) == tuple:
        atom_id, args, choice = atom_id
        return Term('ad_%s_%s' % (atom_id, choice), *args)
    else:
        node = db.getNode(atom_id)
        return Term(node.functor, *node.args)


def builtin_sample(term, result, target=None, engine=None, callback=None, **kwdargs):
    # TODO wrong error message when call argument is wrong
    check_mode((term, result), 'cv', functor='sample')
    # Find the define node for the given query term.
    term_call = term.withArgs(*term.args)
    results = engine.call(term_call, subcall=True, target=target, **kwdargs)
    actions = []
    n = len(term.args)
    for res, node in results:
        res1 = res[:n]
        res_pass = (term.withArgs(*res1), target.getValue(node))
        actions += callback.notifyResult(res_pass, 0, False)
    actions += callback.notifyComplete()
    return True, actions


def sample(model, n=1, tuples=False, **kwdargs):
    engine = DefaultEngine()
    engine.add_builtin('sample', 2, builtin_sample)
    db = engine.prepare(model)

    i = 0
    while i < n:
        result = engine.ground_all(db, target=SampledFormula())
        evidence_ok = True
        for name, node in result.evidence():
            if node is None:
                evidence_ok = False
                break
        if evidence_ok:
            if tuples:
                yield result.toTuples()
            else:
                yield result.toString(db, **kwdargs)
            i += 1


def estimate(model, n=0, **kwdargs):
    from collections import defaultdict
    engine = DefaultEngine()
    engine.add_builtin('sample', 2, builtin_sample)
    db = engine.prepare(model)

    estimates = defaultdict(float)
    counts = 0.0
    try:
        while n == 0 or counts < n:
            result = engine.ground_all(db, target=SampledFormula())
            evidence_ok = True
            for name, node in result.evidence():
                if node is None:
                    evidence_ok = False
                    break
            if evidence_ok:
                for k, v in result.queries():
                    if v == 0:
                        estimates[k] += 1.0
                counts += 1.0
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
    print ('%% Probability estimate after %d samples:' % counts)
    for k in estimates:
        estimates[k] = estimates[k] / counts
    return estimates


def main(args):
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument('filename')
    parser.add_argument('-N', type=int, dest='n', default=argparse.SUPPRESS, help="Number of samples.")
    parser.add_argument('--with-facts', action='store_true', help="Also output choice facts (default: just queries).")
    parser.add_argument('--with-probability', action='store_true', help="Show probability.")
    parser.add_argument('--as-evidence', action='store_true', help="Output as evidence.")
    parser.add_argument('--oneline', action='store_true', help="Format samples on one line.")
    parser.add_argument('--estimate', action='store_true', help='Estimate probability of queries from samples.')
    parser.add_argument('--timeout', '-t', type=int, default=0,
                        help="Set timeout (in seconds, default=off).")

    args = parser.parse_args(args)

    pl = PrologFile(args.filename)

    if args.timeout:
        start_timer(args.timeout)

    def signal_term_handler(signal, frame):
        sys.exit(143)

    signal.signal(signal.SIGTERM, signal_term_handler)

    if args.estimate:
        results = estimate(pl, **vars(args))
        print (process_result(results))
    else:
        first = True
        for s in sample(pl, **vars(args)):
            if not args.oneline and not first:
                print ('----------------')
            first = False
            print (s)

    if args.timeout:
        stop_timer()

    
if __name__ == '__main__':
    main(sys.argv[1:])