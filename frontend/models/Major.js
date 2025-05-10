const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Department = require('./Department');

const Major = sequelize.define('Major', {
  major_id: {
    type: DataTypes.STRING(10),
    primaryKey: true
  },
  major_name: {
    type: DataTypes.STRING(255),
    allowNull: false,
    unique: true
  },
  department_id: {
    type: DataTypes.STRING(10),
    allowNull: false
  }
}, {
  tableName: 'Major',
  timestamps: false
});

// Associations
Major.belongsTo(Department, {
  foreignKey: 'department_id',
  onDelete: 'CASCADE'
});
Department.hasMany(Major, { foreignKey: 'department_id' });

module.exports = Major;
