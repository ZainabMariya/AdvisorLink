const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Department = require('./Department');

const Advisor = sequelize.define('Advisor', {
  advisor_id: {
    type: DataTypes.STRING(50),
    primaryKey: true
  },
  Fname: {
    type: DataTypes.STRING(20),
    allowNull: false
  },
  Lname: {
    type: DataTypes.STRING(40),
    allowNull: false
  },
  email: {
    type: DataTypes.STRING(255),
    allowNull: false,
    unique: true
  },
  department_id: {
    type: DataTypes.STRING(10),
    allowNull: false
  },
  password: {
    type: DataTypes.STRING(255),
    allowNull: false,
    defaultValue: 'PSU'
  }
}, {
  tableName: 'Advisor',
  timestamps: false
});

// Associations
Advisor.belongsTo(Department, {
  foreignKey: 'department_id',
  onDelete: 'RESTRICT'
});
Department.hasMany(Advisor, { foreignKey: 'department_id' });

module.exports = Advisor;
