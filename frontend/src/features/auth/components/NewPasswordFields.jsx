import { Form, Input } from 'antd';

// Contraseña nueva + confirmación, compartidas por la activación y el cambio propio.
// El mínimo replica el del backend (8); el tope de 72 bytes de bcrypt lo valida el servidor.
export default function NewPasswordFields() {
    return (
        <>
            <Form.Item
                label="Contraseña nueva"
                name="password"
                rules={[
                    { required: true, message: 'Ingresa la contraseña nueva' },
                    { min: 8, message: 'Debe tener al menos 8 caracteres' },
                ]}
            >
                <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Form.Item
                label="Confirma la contraseña nueva"
                name="confirm"
                dependencies={['password']}
                rules={[
                    { required: true, message: 'Confirma la contraseña nueva' },
                    ({ getFieldValue }) => ({
                        validator: (_, value) =>
                            !value || value === getFieldValue('password')
                                ? Promise.resolve()
                                : Promise.reject(new Error('Las contraseñas no coinciden')),
                    }),
                ]}
            >
                <Input.Password autoComplete="new-password" />
            </Form.Item>
        </>
    );
}
