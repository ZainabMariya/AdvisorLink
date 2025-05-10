const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Advisor = require('./Advisor');
const Major = require('./Major');
const Department = require('./Department');

const Student = sequelize.define('Student', {
  student_id: {
    type: DataTypes.INTEGER,
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
  advisor_id: {
    type: DataTypes.STRING(50),
    allowNull: true
  },
  major_id: {
    type: DataTypes.STRING(10),
    allowNull: false
  },
  department_id: {
    type: DataTypes.STRING(10),
    allowNull: false
  },
  current_gpa: {
    type: DataTypes.FLOAT,
    allowNull: true
  },
  cumulative_gpa: {
    type: DataTypes.FLOAT,
    allowNull: true
  },
  transcript: {
    type: DataTypes.TEXT,
    allowNull: true
  },
  Warnings: {
    type: DataTypes.STRING(500),
    allowNull: true
  },
  password: {
    type: DataTypes.STRING(255),
    allowNull: false,
    defaultValue: 'PSU'
  },
  completed_hours:{
    type: DataTypes.INTEGER,
    allowNull: true
  },

  enrollment_year:{
    type: DataTypes.INTEGER,
    allowNull: false
  }
}, {
  tableName: 'Student',
  timestamps: false
});

// Associations
Student.belongsTo(Advisor, { foreignKey: 'advisor_id' });
Advisor.hasMany(Student, { foreignKey: 'advisor_id' });

Student.belongsTo(Major, { foreignKey: 'major_id' });
Major.hasMany(Student, { foreignKey: 'major_id' });

Student.belongsTo(Department, { foreignKey: 'department_id' });
Department.hasMany(Student, { foreignKey: 'department_id' });

module.exports = Student;
