// Fuerza y reglas de la contraseña, portadas del indicador de mariachi. El backend aplica
// la misma política (mínimo 8 y al menos 2 de las 3 familias) en validators.py.
const LABELS = ['', 'Muy débil', 'Débil', 'Aceptable', 'Buena'];

const defaultRules = () => ({ length: false, case: false, number: false, special: false });

export const computePasswordStrength = (pwd) => {
    if (!pwd) return { score: 0, label: '', rules: defaultRules() };

    const rules = {
        length: pwd.length >= 8,
        case: /[a-z]/.test(pwd) && /[A-Z]/.test(pwd),
        number: /\d/.test(pwd),
        special: /[^A-Za-z0-9]/.test(pwd),
    };

    const score = Object.values(rules).filter(Boolean).length;
    return { score, label: LABELS[score] || '', rules };
};

export const isStrongEnough = (pwd) => {
    const { score, rules } = computePasswordStrength(pwd);
    return rules.length && score >= 3;
};
